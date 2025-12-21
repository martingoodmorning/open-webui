import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


def infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """推断列类型，返回 {列名: 类型}，类型为 number/category/datetime。

    - 优先使用 pandas 的 dtype 和 to_datetime 进行判断；
    - 尽量保持简单稳健，避免在大数据量上产生过大开销。
    """

    types: Dict[str, str] = {}

    for col in df.columns:
        series = df[col]

        # 跳过全空列
        if series.dropna().empty:
            types[str(col)] = "category"
            continue

        dtype = str(series.dtype).lower()

        # 数值类型
        if any(x in dtype for x in ["int", "float", "decimal"]):
            types[str(col)] = "number"
            continue

        # 日期时间类型
        if "datetime" in dtype or "datetimetz" in dtype:
            types[str(col)] = "datetime"
            continue

        # 尝试将部分非空样本解析为日期
        sample = series.dropna().head(20)
        try:
            parsed = pd.to_datetime(sample, errors="coerce", infer_datetime_format=True)
            non_null = parsed.notna().sum()
            if non_null > 0 and non_null / max(len(sample), 1) >= 0.6:
                types[str(col)] = "datetime"
                continue
        except Exception:
            # 忽略日期解析错误，继续后续判断
            pass

        # 其他情况按类别处理
        types[str(col)] = "category"

    return types


def get_excel_structure(file_path: Path, max_rows: int = 100) -> Dict[str, Any]:
    """获取 Excel/CSV 文件的结构信息。

    返回字典格式：
    {
      "sheets": [
        {
          "name": "sheet 名",
          "columns": [{"name": 列名, "type": 类型}, ...],
          "sample_rows": [[...], ...],
          "total_rows": 总行数,
          "truncated": bool
        },
        ...
      ]
    }
    """

    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))

    suffix = file_path.suffix.lower()
    sheets: List[Dict[str, Any]] = []

    try:
        if suffix in {".xlsx", ".xls", ".xlsm", ".xltx", ".xlt", ".xlsb"}:
            # 先读取所有 sheet 名
            # 使用 ExcelFile 以避免多次打开文件
            if suffix == ".xlsb":
                excel = pd.ExcelFile(file_path, engine="pyxlsb")
            else:
                excel = pd.ExcelFile(file_path, engine="openpyxl")

            for sheet_name in excel.sheet_names:
                df_full = excel.parse(sheet_name=sheet_name)
                total_rows = int(df_full.shape[0])

                # 样本行
                df_sample = df_full.head(max_rows)
                col_types = infer_column_types(df_sample)

                sample_rows: List[List[Any]] = [
                    [
                        (v.isoformat() if hasattr(v, "isoformat") else v)
                        for v in row
                    ]
                    for row in df_sample.itertuples(index=False, name=None)
                ]

                sheets.append(
                    {
                        "name": sheet_name,
                        "columns": [
                            {"name": str(col), "type": col_types.get(str(col), "category")}
                            for col in df_full.columns
                        ],
                        "sample_rows": sample_rows,
                        "total_rows": total_rows,
                        "truncated": total_rows > max_rows,
                    }
                )

        elif suffix == ".csv":
            # CSV 视为单个 sheet
            df_full = pd.read_csv(file_path)
            total_rows = int(df_full.shape[0])
            df_sample = df_full.head(max_rows)
            col_types = infer_column_types(df_sample)

            sample_rows = [
                [
                    (v.isoformat() if hasattr(v, "isoformat") else v)
                    for v in row
                ]
                for row in df_sample.itertuples(index=False, name=None)
            ]

            sheets.append(
                {
                    "name": file_path.stem,
                    "columns": [
                        {"name": str(col), "type": col_types.get(str(col), "category")}
                        for col in df_full.columns
                    ],
                    "sample_rows": sample_rows,
                    "total_rows": total_rows,
                    "truncated": total_rows > max_rows,
                }
            )

        else:
            raise ValueError(f"Unsupported file extension for Excel preview: {suffix}")

    except Exception as e:
        log.exception(e)
        raise

    return {"sheets": sheets}


def build_excel_chart(file_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """根据配置构建 Excel/CSV 图表数据和 Vega-Lite 规范。

    预期的 config 结构：
    {
      "sheet_name": str | None,
      "chart_type": "bar" | "line" | "pie",
      "x_field": str,
      "y_fields": [str],
      "series_field": str | None,
      "agg": "sum" | "count" | "avg",
      "filters": [
        { "field": str, "op": "eq" | "in" | "neq" | "gte" | "lte", "value": Any, "values": [Any] }
      ]
    }

    返回结构：
    {
      "chart_type": str,
      "x_field": str,
      "y_fields": [str],
      "series": [
        { "name": str, "data": [ {"x": Any, "y": float}, ... ] }
      ],
      "vega_spec": { ... }
    }
    """

    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))

    suffix = file_path.suffix.lower()

    chart_type = (config.get("chart_type") or "bar").lower()
    agg = (config.get("agg") or "sum").lower()
    x_field = config.get("x_field")
    y_fields = config.get("y_fields") or []
    series_field = config.get("series_field")
    sheet_name = config.get("sheet_name")
    filters = config.get("filters") or []

    if chart_type not in {"bar", "line", "pie"}:
        raise ValueError(f"Unsupported chart_type: {chart_type}")

    if agg not in {"sum", "count", "avg"}:
        raise ValueError(f"Unsupported aggregation: {agg}")

    if not x_field:
        raise ValueError("x_field is required")

    # 饼图暂不支持多系列
    if chart_type == "pie" and series_field:
        raise ValueError("pie chart does not support series_field currently")

    # 读取数据
    try:
        if suffix in {".xlsx", ".xls", ".xlsm", ".xltx", ".xlt", ".xlsb"}:
            if not sheet_name:
                raise ValueError("sheet_name is required for Excel files")

            engine = "pyxlsb" if suffix == ".xlsb" else "openpyxl"
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine)
        elif suffix == ".csv":
            df = pd.read_csv(file_path)
        else:
            raise ValueError(f"Unsupported file extension for Excel chart: {suffix}")
    except Exception as e:
        log.exception(e)
        raise

    if df.empty:
        raise ValueError("Excel sheet is empty")

    # 应用过滤条件
    if filters:
        mask = pd.Series(True, index=df.index)
        for f in filters:
            field = f.get("field")
            op = f.get("op")
            value = f.get("value")
            values = f.get("values")

            if not field or not op:
                continue
            if field not in df.columns:
                continue

            series = df[field]
            if op == "eq":
                cond = series == value
            elif op == "neq":
                cond = series != value
            elif op == "gte":
                cond = series >= value
            elif op == "lte":
                cond = series <= value
            elif op == "in":
                if values is None:
                    values = [value]
                cond = series.isin(values)
            else:
                raise ValueError(f"Unsupported filter op: {op}")

            mask &= cond.fillna(False)

        df = df[mask]

    if df.empty:
        raise ValueError("No data after applying filters")

    group_cols: List[str] = [x_field]
    if series_field:
        group_cols.append(series_field)

    agg_map = {"sum": "sum", "count": "count", "avg": "mean"}

    # 聚合
    if agg == "count":
        grouped = df.groupby(group_cols, dropna=False)
        agg_df = grouped.size().reset_index(name="__value__")
        measure_name = "count"
        y_fields_out = y_fields or [measure_name]
    else:
        if not y_fields:
            raise ValueError("y_fields is required for sum/avg aggregation")
        y_field = y_fields[0]
        if y_field not in df.columns:
            raise ValueError(f"y_field '{y_field}' not found in sheet")

        # 确保用于 sum/avg 的列是数值型，如果不是则尝试进行数值转换
        y_series = df[y_field]
        if not pd.api.types.is_numeric_dtype(y_series):
            converted = pd.to_numeric(y_series, errors="coerce")
            # 如果全部无法转换为数值，则给出友好提示
            if converted.notna().sum() == 0:
                raise ValueError(
                    f"Field '{y_field}' is not numeric and cannot be aggregated with '{agg}'. "
                    "Please choose a numeric column for Y axis."
                )
            df = df.copy()
            df[y_field] = converted

        grouped = df.groupby(group_cols, dropna=False)[y_field]
        agg_df = grouped.agg(agg_map[agg]).reset_index(name="__value__")
        measure_name = y_field
        y_fields_out = [y_field]

    # 排序（趋势图按 X 排序）
    sort_cols = [x_field]
    if series_field:
        sort_cols.append(series_field)
    agg_df = agg_df.sort_values(by=sort_cols)

    # 构建 series 结构
    series_list: List[Dict[str, Any]] = []

    def _to_serializable(v: Any) -> Any:
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v

    if series_field:
        series_map: Dict[str, List[Dict[str, Any]]] = {}
        for _, row in agg_df.iterrows():
            series_name_raw = row[series_field]
            series_name = "(空)" if pd.isna(series_name_raw) else str(series_name_raw)
            series_map.setdefault(series_name, []).append(
                {"x": _to_serializable(row[x_field]), "y": float(row["__value__"])}
            )
        series_list = [
            {"name": name, "data": data} for name, data in series_map.items()
        ]
    else:
        data_points = [
            {"x": _to_serializable(row[x_field]), "y": float(row["__value__"])}
            for _, row in agg_df.iterrows()
        ]
        series_list = [{"name": measure_name, "data": data_points}]

    # 为 Vega-Lite 构造扁平化数据
    vega_values: List[Dict[str, Any]] = []
    for s in series_list:
        name = s["name"]
        for point in s["data"]:
            vega_values.append(
                {
                    "x": point["x"],
                    "y": point["y"],
                    "series": name,
                }
            )

    # 构建 Vega-Lite spec
    vega_spec: Dict[str, Any]
    if chart_type == "bar":
        vega_spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": vega_values},
            "mark": "bar",
            "encoding": {
                "x": {"field": "x", "type": "nominal", "title": x_field},
                "y": {
                    "field": "y",
                    "type": "quantitative",
                    "title": measure_name,
                },
            },
        }
        if len(series_list) > 1:
            vega_spec["encoding"]["color"] = {
                "field": "series",
                "type": "nominal",
                "title": series_field or "series",
            }
    elif chart_type == "line":
        vega_spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": vega_values},
            "mark": "line",
            "encoding": {
                "x": {"field": "x", "type": "temporal", "title": x_field},
                "y": {
                    "field": "y",
                    "type": "quantitative",
                    "title": measure_name,
                },
            },
        }
        if len(series_list) > 1:
            vega_spec["encoding"]["color"] = {
                "field": "series",
                "type": "nominal",
                "title": series_field or "series",
            }
    elif chart_type == "pie":
        # 饼图以 x 作为类别
        vega_spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": vega_values},
            "mark": {"type": "arc", "tooltip": True},
            "encoding": {
                "theta": {
                    "field": "y",
                    "type": "quantitative",
                    "title": measure_name,
                },
                "color": {"field": "x", "type": "nominal", "title": x_field},
            },
        }
    else:
        # 理论上不会走到这里
        raise ValueError(f"Unsupported chart_type: {chart_type}")

    return {
        "chart_type": chart_type,
        "x_field": x_field,
        "y_fields": y_fields_out,
        "series": series_list,
        "vega_spec": vega_spec,
    }


__all__ = ["infer_column_types", "get_excel_structure", "build_excel_chart"]

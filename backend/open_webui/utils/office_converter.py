"""
Office 文档转 PDF 工具
支持中文字体和 Excel 表格单页显示
"""
import os
import sys
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional

from open_webui.utils.font_config import ensure_chinese_fonts, get_font_env

log = logging.getLogger(__name__)


def convert_office_to_pdf(file_path: Path, output_path: Optional[Path] = None) -> Optional[Path]:
    """
    将 Office 文档转换为 PDF
    支持: .doc, .docx, .xls, .xlsx, .ppt, .pptx
    
    Args:
        file_path: 源文件路径
        output_path: 输出 PDF 路径（可选，默认在源文件同目录）
    
    Returns:
        转换后的 PDF 文件路径，失败返回 None
    """
    try:
        # 检查 LibreOffice 是否可用
        result = subprocess.run(
            ["which", "libreoffice"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            log.warning("LibreOffice not found, Office document preview unavailable")
            return None
        
        # 确保中文字体可用
        ensure_chinese_fonts()

        file_ext = file_path.suffix.lower()
        is_excel = file_ext in ['.xls', '.xlsx']
        
        # 创建临时目录用于输出 PDF
        with tempfile.TemporaryDirectory() as temp_dir:
            # 处理包含中文的文件名：复制到临时位置并使用英文文件名
            # LibreOffice 在处理包含非 ASCII 字符的文件名时可能有问题
            temp_file_path = Path(temp_dir) / f"temp_file{file_ext}"
            import shutil
            shutil.copy2(file_path, temp_file_path)
            
            # 对于 Excel 文件，使用 Python 脚本通过 UNO API 转换
            if is_excel:
                pdf_path = _convert_excel_with_uno(temp_file_path, temp_dir)
            else:
                # 其他文件类型使用命令行转换
                pdf_path = _convert_with_cli(temp_file_path, temp_dir)
            
            if not pdf_path or not pdf_path.exists():
                log.error(f"PDF file not generated. Expected path: {pdf_path}")
                log.error(f"Temp directory contents: {list(Path(temp_dir).iterdir()) if Path(temp_dir).exists() else 'Directory does not exist'}")
                return None

            # 确定最终输出路径
            if output_path:
                final_path = output_path
            else:
                final_path = file_path.parent / f"{file_path.stem}_preview.pdf"
            
            # 确保输出目录存在
            final_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 如果已存在，先删除（确保使用最新的转换结果）
            if final_path.exists():
                try:
                    final_path.unlink()
                    log.info(f"Removed existing preview cache: {final_path}")
                except Exception as e:
                    log.warning(f"Failed to remove existing preview cache: {e}")
            
            import shutil
            shutil.copy2(pdf_path, final_path)
            
            log.info(f"Successfully converted {file_path.name} to PDF: {final_path}")
            return final_path

    except subprocess.TimeoutExpired:
        log.error(f"LibreOffice conversion timeout for file: {file_path}")
        return None
    except Exception as e:
        log.exception(e)
        log.error(f"Error converting Office document to PDF: {file_path}, error: {str(e)}")
        return None


def _convert_with_cli(file_path: Path, output_dir: str) -> Optional[Path]:
    """使用命令行转换（Word、PowerPoint）"""
    # 使用绝对路径，避免路径问题
    abs_file_path = file_path.resolve()
    abs_output_dir = Path(output_dir).resolve()
    
    cmd = [
        "libreoffice",
        "--headless",
        "--nodefault",
        "--nolockcheck",
        "--nologo",
        "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(abs_output_dir),
        str(abs_file_path)
    ]
    
    # 使用字体配置工具获取环境变量
    env = get_font_env()
    
    log.info(f"Converting {abs_file_path.name} to PDF in {abs_output_dir}")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(abs_output_dir)  # 设置工作目录
    )

    if result.returncode != 0:
        log.error(f"LibreOffice conversion failed for {file_path.name}")
        log.error(f"Command: {' '.join(cmd)}")
        log.error(f"Return code: {result.returncode}")
        log.error(f"Stdout: {result.stdout}")
        log.error(f"Stderr: {result.stderr}")
        return None

    # LibreOffice 生成的 PDF 文件名基于输入文件名（不含扩展名）
    pdf_filename = file_path.stem + ".pdf"
    pdf_path = abs_output_dir / pdf_filename
    
    # 如果找不到，尝试列出所有 PDF 文件
    if not pdf_path.exists():
        pdf_files = list(abs_output_dir.glob("*.pdf"))
        log.warning(f"Expected PDF not found: {pdf_path}")
        log.warning(f"Found PDF files in output directory: {pdf_files}")
        if pdf_files:
            # 使用找到的第一个 PDF 文件
            pdf_path = pdf_files[0]
            log.info(f"Using found PDF file: {pdf_path}")
        else:
            log.error(f"PDF file not found after conversion: {pdf_path}")
            log.error(f"Output directory contents: {list(abs_output_dir.iterdir())}")
            log.error(f"LibreOffice stdout: {result.stdout}")
            log.error(f"LibreOffice stderr: {result.stderr}")
            return None
    
    log.info(f"Successfully generated PDF: {pdf_path}")
    return pdf_path


def _convert_excel_with_uno(file_path: Path, output_dir: str) -> Optional[Path]:
    """Excel 转换（使用优化的命令行参数）"""
    # 直接使用优化的命令行参数，UNO API 方案过于复杂
    # 使用最佳实践参数来尽量适应页面
    return _convert_excel_with_cli_fallback(file_path, output_dir)


def _convert_excel_with_cli_fallback(file_path: Path, output_dir: str) -> Optional[Path]:
    """Excel 命令行转换的备用方案（使用最佳参数）"""
    # 使用绝对路径，避免路径问题
    abs_file_path = file_path.resolve()
    abs_output_dir = Path(output_dir).resolve()
    
    # 使用优化的参数，尽量适应页面
    cmd = [
        "libreoffice",
        "--headless",
        "--nodefault",
        "--nolockcheck",
        "--nologo",
        "--norestore",
        "--convert-to", "pdf:calc_pdf_Export:{\"UseTaggedPDF\":true,\"Quality\":100,\"SelectPdfVersion\":1}",
        "--outdir", str(abs_output_dir),
        str(abs_file_path)
    ]
    
    # 使用字体配置工具获取环境变量
    env = get_font_env()
    
    log.info(f"Converting Excel {abs_file_path.name} to PDF in {abs_output_dir}")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(abs_output_dir)  # 设置工作目录
    )

    if result.returncode != 0:
        log.error(f"LibreOffice Excel conversion failed for {file_path.name}")
        log.error(f"Command: {' '.join(cmd)}")
        log.error(f"Return code: {result.returncode}")
        log.error(f"Stdout: {result.stdout}")
        log.error(f"Stderr: {result.stderr}")
        return None

    # LibreOffice 生成的 PDF 文件名基于输入文件名（不含扩展名）
    pdf_filename = file_path.stem + ".pdf"
    pdf_path = abs_output_dir / pdf_filename
    
    # 如果找不到，尝试列出所有 PDF 文件
    if not pdf_path.exists():
        pdf_files = list(abs_output_dir.glob("*.pdf"))
        log.warning(f"Expected PDF not found: {pdf_path}")
        log.warning(f"Found PDF files in output directory: {pdf_files}")
        if pdf_files:
            # 使用找到的第一个 PDF 文件
            pdf_path = pdf_files[0]
            log.info(f"Using found PDF file: {pdf_path}")
        else:
            log.error(f"PDF file not found after Excel conversion: {pdf_path}")
            log.error(f"Output directory contents: {list(abs_output_dir.iterdir())}")
            log.error(f"LibreOffice stdout: {result.stdout}")
            log.error(f"LibreOffice stderr: {result.stderr}")
            return None
    
    log.info(f"Successfully generated PDF: {pdf_path}")
    return pdf_path


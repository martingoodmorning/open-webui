<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import * as echarts from 'echarts';

	import Spinner from '../common/Spinner.svelte';
	import {
		getSharedExcelPreview,
		getSharedExcelChart,
		getSharedExcelTemplates
	} from '$lib/apis/files/shared';

	const i18n = getContext('i18n');

	export let file: any;
	export let onClose: () => void;

	let loadingPreview = false;
	let loadingChart = false;
	let previewError: string | null = null;
	let chartError: string | null = null;

	let sheets: any[] = [];
	let selectedSheetName: string | null = null;
	let columns: any[] = [];
	let numericColumns: any[] = [];
	let yAxisColumns: any[] = [];

	let templates: any[] = [];
	let selectedTemplateId: string = '';

	let chartType = 'bar'; // bar | line | pie
	let agg = 'sum'; // sum | count | avg
	let xField = '';
	let yField = '';
	let seriesField = '';

	let chartContainer: HTMLDivElement;
	let chartInstance: any = null;
	let resizeHandler: (() => void) | null = null;

	const initFromSheet = () => {
		const sheet = sheets.find((s) => s.name === selectedSheetName) || sheets[0];
		if (!sheet) {
			columns = [];
			xField = '';
			yField = '';
			seriesField = '';
			return;
		}
		columns = sheet.columns || [];

		// 简单的默认字段选择：优先数值列作为 Y，其他列作为 X
		const numericCols = columns.filter((c) => c.type === 'number');
		const datetimeCols = columns.filter((c) => c.type === 'datetime');

		xField = xField || (datetimeCols[0]?.name ?? columns[0]?.name ?? '');
		yField = yField || (numericCols[0]?.name ?? columns[1]?.name ?? '');
		seriesField = seriesField || '';
	};

	// 根据列和聚合方式动态计算可选的 Y 轴字段：
	// - sum/avg：只允许数值列
	// - count：允许全部列（也可以留空）
	$: numericColumns = (columns || []).filter((c) => c.type === 'number');
	$: yAxisColumns = agg === 'count' ? columns || [] : numericColumns;

	// 当聚合方式或列变化导致当前 yField 不再合法时，自动清空
	$: if (yField && !yAxisColumns.find((c) => c.name === yField)) {
		yField = '';
	}

	const loadPreview = async () => {
		if (!file?.id) return;
		loadingPreview = true;
		previewError = null;

		try {
			const res = await getSharedExcelPreview(localStorage.token, file.id, 100);
			sheets = res?.sheets ?? [];
			selectedSheetName = sheets[0]?.name ?? null;
			initFromSheet();
		} catch (error: any) {
			const message = typeof error === 'string' ? error : error?.message || '加载 Excel 结构失败';
			previewError = message;
			toast.error(message);
		} finally {
			loadingPreview = false;
		}
	};

	const loadTemplates = async () => {
		try {
			const res = await getSharedExcelTemplates(localStorage.token);
			templates = res || [];
		} catch (error) {
			console.error('加载 Excel 模版失败:', error);
		}
	};

	const handleSheetChange = () => {
		if (chartInstance) {
			chartInstance.clear();
		}
		chartError = null;
		xField = '';
		yField = '';
		seriesField = '';
		initFromSheet();
	};

	const applyTemplate = (tpl: any) => {
		if (!tpl) return;

		// 切换到首选 sheet（如果存在）
		if (tpl.preferred_sheet && sheets.some((s) => s.name === tpl.preferred_sheet)) {
			selectedSheetName = tpl.preferred_sheet;
			handleSheetChange();
		}

		// 应用图表类型和聚合方式
		if (tpl.chart_type) {
			chartType = tpl.chart_type;
		}
		if (tpl.default_agg) {
			agg = tpl.default_agg;
		}

		// 按列名匹配字段
		const cols = columns || [];
		if (tpl.default_x && cols.some((c) => c.name === tpl.default_x)) {
			xField = tpl.default_x;
		}
		if (tpl.default_y && cols.some((c) => c.name === tpl.default_y)) {
			yField = tpl.default_y;
		}
		if (tpl.default_series && cols.some((c) => c.name === tpl.default_series)) {
			seriesField = tpl.default_series;
		}
	};

	const handleTemplateChange = () => {
		if (!selectedTemplateId) return;
		const tpl = templates.find((t) => t.id === selectedTemplateId);
		if (!tpl) return;
		applyTemplate(tpl);
	};

	const downloadChart = () => {
		if (!chartInstance) {
			toast.warning('请先生成图表');
			return;
		}

		try {
			const dataUrl = chartInstance.getDataURL({
				type: 'png',
				pixelRatio: 2,
				backgroundColor: '#ffffff'
			});

			const link = document.createElement('a');
			const baseName =
				(file?.filename || 'chart').replace(/\.[^/.]+$/, '') || 'chart';
			link.href = dataUrl;
			link.download = `${baseName}_chart.png`;
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
		} catch (error) {
			console.error('导出图表失败:', error);
			toast.error('导出图表失败，请稍后重试');
		}
	};

	const buildChart = async () => {
		if (!file?.id) return;
		if (!selectedSheetName) {
			toast.warning('请先选择工作表');
			return;
		}
		if (!xField) {
			toast.warning('请先选择横轴字段');
			return;
		}

		const config: any = {
			sheet_name: selectedSheetName,
			chart_type: chartType,
			x_field: xField,
			y_fields: yField ? [yField] : [],
			series_field: seriesField || null,
			agg,
			filters: []
		};

		loadingChart = true;
		chartError = null;

		try {
			const res = await getSharedExcelChart(localStorage.token, file.id, config);
			const option = buildEchartsOption(res);
			await renderEcharts(option);
		} catch (error: any) {
			const message = typeof error === 'string' ? error : error?.message || '生成图表失败';
			chartError = message;
			toast.error(message);
		} finally {
			loadingChart = false;
		}
	};

	const buildEchartsOption = (res: any): any => {
		const chart_type = res?.chart_type || chartType;
		const x_field = res?.x_field || xField;
		const y_fields = (res?.y_fields as string[]) || (yField ? [yField] : []);
		const series = (res?.series as any[]) || [];

		if (!series || series.length === 0) {
			throw new Error('图表数据为空');
		}

		if (chart_type === 'pie') {
			const firstSeries = series[0] || { data: [] };
			const data = (firstSeries.data || []).map((p: any) => ({
				name: String(p.x),
				value: p.y
			}));

			return {
				tooltip: { trigger: 'item' },
				legend: { top: 'bottom' },
				series: [
					{
						name: y_fields[0] || '',
						type: 'pie',
						radius: '60%',
						data
					}
				]
			};
		}

		// bar / line
		const xSet = new Set<string>();
		for (const s of series) {
			for (const p of s.data || []) {
				xSet.add(String(p.x));
			}
		}
		const categories = Array.from(xSet);

		const echartsSeries = series.map((s) => {
			const map = new Map<string, number>();
			for (const p of s.data || []) {
				map.set(String(p.x), p.y);
			}
			return {
				name: s.name,
				type: chart_type === 'line' ? 'line' : 'bar',
				data: categories.map((x) => map.get(x) ?? 0)
			};
		});

		return {
			tooltip: { trigger: 'axis' },
			legend: { top: 0 },
			grid: { top: 40, left: 40, right: 20, bottom: 40 },
			xAxis: {
				type: 'category',
				data: categories,
				name: x_field
			},
			yAxis: {
				type: 'value',
				name: y_fields[0] || ''
			},
			series: echartsSeries
		};
	};

	const renderEcharts = async (option: any) => {
		if (!chartContainer) {
			throw new Error('图表容器未就绪');
		}

		if (!chartInstance) {
			chartInstance = echarts.init(chartContainer);
		}

		chartInstance.setOption(option, true);

		if (typeof window !== 'undefined' && !resizeHandler) {
			resizeHandler = () => {
				if (chartInstance) {
					chartInstance.resize();
				}
			};
			window.addEventListener('resize', resizeHandler);
		}
	};

	onMount(() => {
		loadPreview();
		loadTemplates();
	});

	onDestroy(() => {
		if (chartInstance) {
			chartInstance.dispose();
			chartInstance = null;
		}
		if (typeof window !== 'undefined' && resizeHandler) {
			window.removeEventListener('resize', resizeHandler);
			resizeHandler = null;
		}
	});
</script>

<div class="flex flex-col gap-3">
	<div class="flex flex-col md:flex-row gap-3">
		<!-- 配置区域 -->
		<div class="w-full md:w-1/2 flex flex-col gap-2 text-sm">
			<div class="font-medium text-gray-900 dark:text-gray-100">
				Excel 可视化配置
			</div>

			{#if loadingPreview}
				<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
					<Spinner className="size-3" />
					<span>正在加载工作表结构...</span>
				</div>
			{:else if previewError}
				<div class="text-xs text-red-500 dark:text-red-400">
					{previewError}
				</div>
			{:else if (sheets ?? []).length === 0}
				<div class="text-xs text-gray-500 dark:text-gray-400">
					未在该文件中检测到可用的工作表或数据。
				</div>
			{:else}
				<div class="grid grid-cols-1 gap-2">
					{#if (templates ?? []).length > 0}
						<div class="flex flex-col gap-1">
							<label class="text-xs text-gray-500 dark:text-gray-400">内置模版（可选）</label>
							<select
								class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
								bind:value={selectedTemplateId}
								on:change={handleTemplateChange}
							>
								<option value="">不使用模版</option>
								{#each templates as tpl}
									<option value={tpl.id}>{tpl.name}</option>
								{/each}
							</select>
							{#if selectedTemplateId}
								<p class="text-[11px] text-gray-500 dark:text-gray-400">
									{templates.find((t) => t.id === selectedTemplateId)?.description}
								</p>
							{/if}
						</div>
					{/if}

					<div class="flex flex-col gap-1">
						<label class="text-xs text-gray-500 dark:text-gray-400">工作表</label>
						<select
							class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
							bind:value={selectedSheetName}
							on:change={handleSheetChange}
						>
							{#each sheets as sheet}
								<option value={sheet.name}>{sheet.name}</option>
							{/each}
						</select>
					</div>

					<div class="flex gap-2">
						<div class="flex-1 flex flex-col gap-1">
							<label class="text-xs text-gray-500 dark:text-gray-400">图表类型</label>
							<select
								class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
								bind:value={chartType}
							>
								<option value="bar">柱状图</option>
								<option value="line">趋势图（折线）</option>
								<option value="pie">饼图</option>
							</select>
						</div>
						<div class="flex-1 flex flex-col gap-1">
							<label class="text-xs text-gray-500 dark:text-gray-400">聚合方式</label>
							<select
								class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
								bind:value={agg}
							>
								<option value="sum">求和</option>
								<option value="count">计数</option>
								<option value="avg">平均值</option>
							</select>
						</div>
					</div>

					<div class="flex flex-col gap-1">
						<label class="text-xs text-gray-500 dark:text-gray-400">X 轴字段</label>
						<select
							class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
							bind:value={xField}
						>
							<option value="">请选择</option>
							{#each columns as col}
								<option value={col.name}>
									{col.name} ({col.type})
								</option>
							{/each}
						</select>
					</div>

					<div class="flex flex-col gap-1">
						<label class="text-xs text-gray-500 dark:text-gray-400"
							>Y 轴字段（数值列，计数时可留空）</label
						>
						<select
							class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
							bind:value={yField}
						>
							<option value="">（计数时可留空）</option>
							{#each yAxisColumns as col}
								<option value={col.name}>
									{col.name} ({col.type})
								</option>
							{/each}
						</select>
					</div>

					<div class="flex flex-col gap-1">
						<label class="text-xs text-gray-500 dark:text-gray-400"
							>分组字段（可选，多系列）</label
						>
						<select
							class="rounded-lg border border-gray-200 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
							bind:value={seriesField}
						>
							<option value="">（不分组）</option>
							{#each columns as col}
								<option value={col.name}>
									{col.name} ({col.type})
								</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="flex gap-2 mt-2">
					<button
						class="px-3 py-1.5 rounded-xl bg-black text-white dark:bg-white dark:text-black text-xs font-medium flex items-center gap-2 disabled:opacity-50"
						on:click={buildChart}
						disabled={loadingChart}
						type="button"
					>
						{#if loadingChart}
							<Spinner className="size-3" />
							<span>生成中...</span>
						{:else}
							<span>生成图表</span>
						{/if}
					</button>
					<button
						class="px-3 py-1.5 rounded-xl border border-blue-200 dark:border-blue-800 text-xs text-blue-600 dark:text-blue-400 flex items-center gap-2"
						on:click={downloadChart}
						type="button"
					>
						<span>下载图表</span>
					</button>
					<button
						class="px-3 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-300"
						on:click={onClose}
						type="button"
					>
						关闭
					</button>
				</div>
				{/if}
			</div>

		<!-- 图表区域 -->
				<div class="w-full md:w-1/2 flex flex-col gap-2">
			<div class="font-medium text-gray-900 dark:text-gray-100 text-sm">图表预览</div>
			<div class="border border-dashed border-gray-200 dark:border-gray-700 rounded-2xl min-h-[220px] bg-gray-50/50 dark:bg-gray-900/60 px-2 py-3 flex flex-col gap-2">
				{#if loadingChart}
					<div class="flex flex-col items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
						<Spinner className="size-4" />
						<span>正在生成图表...</span>
					</div>
				{:else if chartError}
					<div class="text-xs text-red-500 dark:text-red-400 text-center px-2">
						{chartError}
					</div>
				{:else if !chartInstance}
					<div class="text-xs text-gray-500 dark:text-gray-400 text-center px-2">
						请选择字段并点击“生成图表”。
					</div>
				{/if}
				<div class="w-full max-h-[360px] overflow-auto mt-1">
					<div bind:this={chartContainer} class="w-full min-h-[260px]" />
				</div>
			</div>
		</div>
	</div>
</div>

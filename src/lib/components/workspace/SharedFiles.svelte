<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, onDestroy, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, user } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { getSharedFiles, uploadSharedFile, downloadSharedFile, deleteSharedFile, getSharedFilePreviewUrl } from '$lib/apis/files/shared';
	import { getGroups } from '$lib/apis/groups';
	import { Select } from 'bits-ui';
	import { goto } from '$app/navigation';

	import DeleteConfirmDialog from '../common/ConfirmDialog.svelte';
	import Badge from '../common/Badge.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Spinner from '../common/Spinner.svelte';
	import XMark from '../icons/XMark.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Download from '../icons/Download.svelte';
	import ChevronDown from '../icons/ChevronDown.svelte';
	import Check from '../icons/Check.svelte';
	import CheckBox from '../icons/CheckBox.svelte';
	import Eye from '../icons/Eye.svelte';
	import Modal from '../common/Modal.svelte';
	import Document from '../icons/Document.svelte';
	import Photo from '../icons/Photo.svelte';
	import Folder from '../icons/Folder.svelte';
	import ChatBubble from '../icons/ChatBubble.svelte';

	let loaded = false;
	let loading = false;
	let uploading = false;

	let query = '';
	let selectedItem: any = null;
	let showDeleteConfirm = false;
	let previewItem: any = null;
	let showPreview = false;
	let previewUrl = '';
	let loadingPreview = false;

	let files: any[] = [];
	let total = 0;
	let page = 1;
	let pageSize = 20;
	
	// 搜索防抖
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;

	// 批量操作相关
	let selectedFileIds: Set<string> = new Set();
	let batchMode = false;

	let fileInput: HTMLInputElement;

	// 分组相关
	let groups: any[] = [];
	let selectedGroupId: string | null = null; // null 表示"全部"，'global' 表示全局共享
	
	// 上传对话框相关
	let showUploadDialog = false;
	let uploadGroupId: string | null = 'global'; // 上传时选择的分组，默认为全局共享

	const loadGroups = async () => {
		try {
			const res = await getGroups(localStorage.token);
			if (res) {
				groups = res || [];
			}
		} catch (error) {
			console.error('加载分组列表失败:', error);
		}
	};

	const loadFiles = async () => {
		loading = true;
		try {
			const res = await getSharedFiles(
				localStorage.token,
				page,
				pageSize,
				selectedGroupId === 'global' ? 'global' : selectedGroupId || undefined,
				'updated_at',
				'desc',
				query || undefined
			);
			if (res) {
				files = res.items || [];
				total = res.total || 0;
			}
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			loading = false;
			loaded = true;
		}
	};
	
	// 搜索防抖处理
	$: if (query !== undefined) {
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}
		searchTimeout = setTimeout(() => {
			page = 1; // 搜索时重置到第一页
			loadFiles();
		}, 300);
	}

	// 保存选择的分组ID，用于上传
	let selectedUploadGroupId: string | null = 'global';
	// 使用闭包变量保存分组ID，防止被重置
	let pendingUploadGroupId: string | null = null;

	const openUploadDialog = () => {
		// 重置上传分组为默认值
		uploadGroupId = 'global';
		selectedUploadGroupId = 'global';
		pendingUploadGroupId = null;
		showUploadDialog = true;
	};

	const confirmUploadGroup = () => {
		// 使用当前选择的分组ID（优先使用 uploadGroupId，因为它是最新的选择）
		const finalGroupId = uploadGroupId || selectedUploadGroupId || 'global';
		selectedUploadGroupId = finalGroupId;
		// 保存到闭包变量中，确保上传时能获取到
		pendingUploadGroupId = finalGroupId;
		// 同时保存到文件输入框的 data 属性中，作为备用方案
		if (fileInput) {
			fileInput.dataset.groupId = finalGroupId;
		}
		console.log('确认上传分组，最终使用的分组ID:', finalGroupId, 'uploadGroupId:', uploadGroupId, 'pendingUploadGroupId:', pendingUploadGroupId);
		// 关闭对话框
		showUploadDialog = false;
		// 触发文件选择
		setTimeout(() => {
			fileInput?.click();
		}, 100);
	};

		const uploadHandler = async (event: Event) => {
		const target = event.target as HTMLInputElement;
		const files = target.files;
		if (!files || files.length === 0) return;

		// 优先使用文件输入框的 data-group-id 属性（最可靠），然后是 pendingUploadGroupId，最后是 selectedUploadGroupId
		const dataGroupId = target.dataset.groupId;
		const currentGroupId = dataGroupId || pendingUploadGroupId || selectedUploadGroupId || 'global';
		console.log('uploadHandler 开始，当前分组ID:', currentGroupId, 'dataGroupId:', dataGroupId, 'pendingUploadGroupId:', pendingUploadGroupId, 'selectedUploadGroupId:', selectedUploadGroupId);
		
		// 清除临时变量
		pendingUploadGroupId = null;
		if (target.dataset.groupId) {
			delete target.dataset.groupId;
		}

		uploading = true;
		let successCount = 0;
		let failCount = 0;

		try {
			// 遍历所有选中的文件，逐个上传
			for (let i = 0; i < files.length; i++) {
				const file = files[i];
				try {
					// 使用保存的分组ID（使用闭包中的 currentGroupId，确保不会被重置）
					const groupId = currentGroupId;
					console.log('准备上传文件:', {
						fileName: file.name,
						currentGroupId: currentGroupId,
						selectedUploadGroupId: selectedUploadGroupId,
						groupId: groupId
					});
					// 如果 groupId 是 'global' 或 null，传递 'global'；否则传递实际的分组ID
					const finalGroupId = (groupId === 'global' || !groupId) ? 'global' : groupId;
					console.log('实际上传的分组ID:', finalGroupId);
					await uploadSharedFile(localStorage.token, file, finalGroupId);
					successCount++;
				} catch (error) {
					failCount++;
					console.error(`文件 ${file.name} 上传失败:`, error);
				}
			}

			// 显示上传结果
			if (successCount > 0 && failCount === 0) {
				toast.success(`成功上传 ${successCount} 个文件`);
			} else if (successCount > 0 && failCount > 0) {
				toast.warning(`成功上传 ${successCount} 个文件，${failCount} 个文件上传失败`);
			} else {
				toast.error(`所有文件上传失败`);
			}

			// 刷新文件列表
			await loadFiles();
			
			// 关闭对话框（如果还在显示）
			showUploadDialog = false;
		} catch (error) {
			toast.error(`上传过程中发生错误: ${error}`);
			// 即使出错也关闭对话框
			showUploadDialog = false;
		} finally {
			uploading = false;
			if (fileInput) fileInput.value = '';
			// 清除待上传的分组ID
			pendingUploadGroupId = null;
		}
	};

	const downloadHandler = async (fileId: string, originalFilename?: string) => {
		try {
			// 如果提供了原文件名，直接使用；否则从 API 响应中提取
			if (originalFilename) {
				// 使用原文件名直接下载
				const res = await fetch(
					`${WEBUI_API_BASE_URL}/files/shared/${fileId}/download?attachment=true`,
					{
						method: 'GET',
						headers: {
							authorization: `Bearer ${localStorage.token}`
						}
					}
				);
				
				if (!res.ok) {
					const error = await res.json().catch(() => ({ detail: '下载失败' }));
					throw new Error(error.detail || '下载失败');
				}
				
				const blob = await res.blob();
				const url = window.URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = originalFilename; // 使用原文件名
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				window.URL.revokeObjectURL(url);
			} else {
				// 使用 API 函数（会从响应头提取文件名）
				await downloadSharedFile(localStorage.token, fileId, true);
			}
			toast.success('文件下载成功');
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const deleteHandler = async (item: any) => {
		const res = await deleteSharedFile(localStorage.token, item.id).catch((e) => {
			toast.error(`${e}`);
		});

		if (res) {
			await loadFiles();
			toast.success('文件删除成功');
		}
	};

	// 将共享文件转换为聊天文件格式
	const convertSharedFileToChatFile = (item: any) => {
		// 根据文件类型确定 type
		const filename = item.filename?.toLowerCase() || '';
		let fileType = 'file'; // 默认类型：用于检索的文件

		// 图片仍然标记为 image，便于前端按图片处理
		if (
			filename.endsWith('.jpg') ||
			filename.endsWith('.jpeg') ||
			filename.endsWith('.png') ||
			filename.endsWith('.gif') ||
			filename.endsWith('.webp') ||
			filename.endsWith('.svg')
		) {
			fileType = 'image';
		}
		
		// 生成唯一的 itemId（使用时间戳和随机数，避免依赖 uuid 包）
		const itemId = `${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
		
		return {
			type: fileType,
			// 与聊天上传文件结构对齐：主要依赖 id，file 字段在检索时不是必须
			file: item.id,
			id: item.id,
			name: item.filename || item.meta?.name || '未知文件',
			collection_name: '',
			status: 'done',
			error: '',
			itemId: itemId,
			size: item.meta?.size || 0,
			content_type: item.meta?.content_type || '',
			// 为前端预览提供可点击链接（与普通文件保持一致）
			url: `${WEBUI_API_BASE_URL}/files/${item.id}`
		};
	};

	// 发送文件到聊天（单个文件）
	const sendToChatHandler = async (item: any) => {
		try {
			const chatFile = convertSharedFileToChatFile(item);
			
			// 保存到 sessionStorage，供聊天页面读取
			const chatInput = {
				prompt: '',
				files: [chatFile],
				selectedToolIds: [],
				selectedFilterIds: [],
				webSearchEnabled: false,
				imageGenerationEnabled: false,
				codeInterpreterEnabled: false
			};
			
			// 保存到 sessionStorage（新聊天）
			sessionStorage.setItem('chat-input', JSON.stringify(chatInput));
			
			// 跳转到新聊天页面
			await goto('/');
			toast.success('文件已添加到聊天');
		} catch (error) {
			toast.error(`发送到聊天失败: ${error}`);
		}
	};

	// 批量发送文件到聊天
	const batchSendToChat = async () => {
		if (selectedFileIds.size === 0) {
			toast.warning('请先选择要发送的文件');
			return;
		}
		
		try {
			const selectedFiles = files.filter(f => selectedFileIds.has(f.id));
			const chatFiles = selectedFiles.map(item => convertSharedFileToChatFile(item));
			
			// 保存到 sessionStorage，供聊天页面读取
			const chatInput = {
				prompt: '',
				files: chatFiles,
				selectedToolIds: [],
				selectedFilterIds: [],
				webSearchEnabled: false,
				imageGenerationEnabled: false,
				codeInterpreterEnabled: false
			};
			
			// 保存到 sessionStorage（新聊天）
			sessionStorage.setItem('chat-input', JSON.stringify(chatInput));
			
			// 跳转到新聊天页面
			await goto('/');
			toast.success(`已添加 ${chatFiles.length} 个文件到聊天`);
			
			// 退出批量模式
			batchMode = false;
			selectedFileIds.clear();
		} catch (error) {
			toast.error(`批量发送到聊天失败: ${error}`);
		}
	};

	// 批量操作
	const toggleBatchMode = () => {
		batchMode = !batchMode;
		if (!batchMode) {
			selectedFileIds.clear();
		}
	};

	const toggleFileSelection = (fileId: string) => {
		if (selectedFileIds.has(fileId)) {
			selectedFileIds.delete(fileId);
		} else {
			selectedFileIds.add(fileId);
		}
		selectedFileIds = selectedFileIds; // 触发响应式更新
	};

	const selectAllFiles = () => {
		const filteredFiles = files.filter((f) =>
			!query || f.filename.toLowerCase().includes(query.toLowerCase())
		);
		if (selectedFileIds.size === filteredFiles.length) {
			selectedFileIds.clear();
		} else {
			selectedFileIds = new Set(filteredFiles.map((f) => f.id));
		}
		selectedFileIds = selectedFileIds; // 触发响应式更新
	};

	const batchDownload = async () => {
		if (selectedFileIds.size === 0) {
			toast.warning('请先选择要下载的文件');
			return;
		}

		const fileIds = Array.from(selectedFileIds);
		let successCount = 0;
		let failCount = 0;

		for (const fileId of fileIds) {
			try {
				// 查找文件信息以获取原文件名
				const file = files.find(f => f.id === fileId);
				if (file) {
					await downloadHandler(fileId, file.filename);
				} else {
					await downloadSharedFile(localStorage.token, fileId, true);
				}
				successCount++;
				// 添加延迟，避免浏览器阻止多个下载
				await new Promise((resolve) => setTimeout(resolve, 300));
			} catch (error) {
				failCount++;
				console.error(`文件 ${fileId} 下载失败:`, error);
			}
		}

		if (successCount > 0 && failCount === 0) {
			toast.success(`成功下载 ${successCount} 个文件`);
		} else if (successCount > 0 && failCount > 0) {
			toast.warning(`成功下载 ${successCount} 个文件，${failCount} 个文件下载失败`);
		} else {
			toast.error('所有文件下载失败');
		}

		selectedFileIds.clear();
		batchMode = false;
	};

	const batchDelete = async () => {
		if (selectedFileIds.size === 0) {
			toast.warning('请先选择要删除的文件');
			return;
		}

		const confirmed = confirm(`确定要删除选中的 ${selectedFileIds.size} 个文件吗？此操作不可恢复。`);
		if (!confirmed) return;

		const fileIds = Array.from(selectedFileIds);
		let successCount = 0;
		let failCount = 0;

		for (const fileId of fileIds) {
			try {
				await deleteSharedFile(localStorage.token, fileId);
				successCount++;
			} catch (error) {
				failCount++;
				console.error(`文件 ${fileId} 删除失败:`, error);
			}
		}

		if (successCount > 0 && failCount === 0) {
			toast.success(`成功删除 ${successCount} 个文件`);
		} else if (successCount > 0 && failCount > 0) {
			toast.warning(`成功删除 ${successCount} 个文件，${failCount} 个文件删除失败`);
		} else {
			toast.error('所有文件删除失败');
		}

		await loadFiles();
		selectedFileIds.clear();
		batchMode = false;
	};

	const formatFileSize = (bytes: number) => {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
	};

	const formatDate = (timestamp: number) => {
		const date = new Date(timestamp * 1000);
		return date.toLocaleString();
	};

	// 检查是否是 Office 文档
	const isOfficeDocument = (file: any) => {
		if (!file) return false;
		const filename = file.filename?.toLowerCase() || '';
		const contentType = file.meta?.content_type?.toLowerCase() || '';
		return (
			contentType.includes('msword') || 
			contentType.includes('wordprocessingml') ||
			contentType.includes('spreadsheetml') ||
			contentType.includes('presentationml') ||
			['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'].some(ext => filename.endsWith(ext))
		);
	};

	// 获取文件类型图标
	const getFileIcon = (file: any) => {
		if (!file) return Document;
		const filename = file.filename?.toLowerCase() || '';
		const contentType = file.meta?.content_type?.toLowerCase() || '';
		
		// PDF
		if (contentType === 'application/pdf' || filename.endsWith('.pdf')) {
			return Document;
		}
		// 图片
		if (contentType.startsWith('image/') || 
			['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].some(ext => filename.endsWith(ext))) {
			return Photo;
		}
		// Office 文档
		if (isOfficeDocument(file)) {
			return Document;
		}
		// 默认文档图标
		return Document;
	};

	// 获取分组显示名称
	const getGroupDisplayName = (spaceId: string) => {
		if (spaceId === 'global') {
			return '全局共享';
		}
		// 尝试从 groups 列表中查找分组名称
		const group = groups.find(g => g.id === spaceId);
		return group ? group.name : spaceId;
	};
	
	// 高亮搜索关键词
	const highlightSearchText = (text: string, searchText: string) => {
		if (!searchText || !text) return text;
		const regex = new RegExp(`(${searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
		const parts = text.split(regex);
		return parts.map((part, index) => {
			if (regex.test(part)) {
				return `<mark class="bg-yellow-200 dark:bg-yellow-900/50 px-0.5 rounded">${part}</mark>`;
			}
			return part;
		}).join('');
	};

	const isPreviewable = (file: any) => {
		if (!file) return false;
		const filename = file.filename?.toLowerCase() || '';
		const contentType = file.meta?.content_type?.toLowerCase() || '';
		
		// PDF
		if (contentType === 'application/pdf' || filename.endsWith('.pdf')) {
			return true;
		}
		// 图片
		if (contentType.startsWith('image/') || 
			['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].some(ext => filename.endsWith(ext))) {
			return true;
		}
		// 文本文件
		if (contentType.startsWith('text/') || 
			['.txt', '.md', '.json', '.xml', '.csv', '.log'].some(ext => filename.endsWith(ext))) {
			return true;
		}
		// Office 文档
		if (contentType.includes('msword') || 
			contentType.includes('wordprocessingml') ||
			contentType.includes('spreadsheetml') ||
			contentType.includes('presentationml') ||
			['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'].some(ext => filename.endsWith(ext))) {
			return true;
		}
		return false;
	};

	const openPreview = async (item: any) => {
		previewItem = item;
		showPreview = true;
		loadingPreview = true;
		previewUrl = '';

		// 加载预览 URL
		if (isPreviewable(item)) {
			const isOffice = isOfficeDocument(item);
			
			// 优先使用缓存的 blob URL（如果存在且有效）
			if (previewUrls.has(item.id)) {
				const cachedUrl = previewUrls.get(item.id)!;
				try {
					const testResponse = await fetch(cachedUrl, { method: 'HEAD' });
					if (testResponse.ok) {
						previewUrl = cachedUrl;
						loadingPreview = false;
						return;
					}
				} catch {
					// 缓存无效，清理并继续获取新的
					URL.revokeObjectURL(cachedUrl);
					previewUrls.delete(item.id);
				}
			}
			
			// Office 文档使用预览接口（后端会转换为 PDF）
			if (isOffice) {
				try {
					const response = await fetch(getSharedFilePreviewUrl(item.id), {
						headers: {
							authorization: `Bearer ${localStorage.token}`
						}
					});
					
					if (!response.ok) {
						throw new Error('Failed to fetch preview');
					}
					
					const blob = await response.blob();
					const url = URL.createObjectURL(blob);
					previewUrls.set(item.id, url);
					previewUrl = url;
				} catch (error) {
					console.error('Error loading Office preview:', error);
					toast.error('预览加载失败，请确保已安装 LibreOffice');
				}
			} else {
				// 其他文件类型使用下载接口
				previewUrl = await getPreviewUrl(item.id);
			}
		}
		loadingPreview = false;
	};

	let previewUrls: Map<string, string> = new Map();

	// 清理预览 URL - 不立即清理，保留在 Map 中以便下次使用
	// 只在组件卸载或明确需要清理时才 revoke
	$: if (!showPreview) {
		// 只清空 previewUrl 变量，不 revoke blob URL
		// blob URL 保留在 previewUrls Map 中以便下次使用
		previewUrl = '';
	}

	const getPreviewUrl = async (fileId: string) => {
		// 通过 fetch 获取文件内容，创建 blob URL
		try {
			const downloadUrl = `${WEBUI_API_BASE_URL}/files/shared/${fileId}/download?attachment=false`;
			const response = await fetch(
				downloadUrl,
				{
					headers: {
						authorization: `Bearer ${localStorage.token}`
					}
				}
			);

			if (!response.ok) {
				throw new Error('Failed to fetch file');
			}

			const blob = await response.blob();
			const url = URL.createObjectURL(blob);
			previewUrls.set(fileId, url);
			return url;
		} catch (error) {
			console.error('Error loading preview:', error);
			return '';
		}
	};

	// 分组选择器选项
	$: groupOptions = [
		{ value: null, label: '全部' },
		{ value: 'global', label: '全局共享' },
		...groups.map((g) => ({ value: g.id, label: g.name }))
	];

	// 上传分组选择器选项
	$: uploadGroupOptions = [
		{ value: 'global', label: '全局共享' },
		...groups.map((g) => ({ value: g.id, label: g.name }))
	];

	$: selectedGroup = groupOptions.find((g) => g.value === selectedGroupId) || groupOptions[0];
	$: uploadGroup = uploadGroupOptions.find((g) => g.value === uploadGroupId) || uploadGroupOptions[0];

	const onGroupChange = async (groupId: string | null) => {
		selectedGroupId = groupId;
		page = 1; // 切换分组时重置到第一页
		await loadFiles();
	};


	onMount(async () => {
		await loadGroups();
		await loadFiles();
	});

	// 组件卸载时清理所有 blob URL
	onDestroy(() => {
		for (const url of previewUrls.values()) {
			URL.revokeObjectURL(url);
		}
		previewUrls.clear();
		if (previewUrl) {
			URL.revokeObjectURL(previewUrl);
		}
	});
</script>

<svelte:head>
	<title>共享网盘 • {$WEBUI_NAME}</title>
</svelte:head>

{#if loaded}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		on:confirm={() => {
			deleteHandler(selectedItem);
		}}
	/>

	<!-- 文件预览模态框 -->
	{#if showPreview && previewItem}
		<Modal bind:show={showPreview} size="xl">
			<div class="font-primary px-4.5 py-3.5 w-full flex flex-col dark:text-gray-400">
				<div class="pb-2">
					<div class="flex items-start justify-between">
						<div class="flex-1 min-w-0">
							<div class="font-medium text-lg dark:text-gray-100 truncate">
								{previewItem.filename}
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
								{formatFileSize(previewItem.meta?.size || 0)} • {formatDate(previewItem.created_at)}
							</div>
						</div>
						<button
							class="flex-shrink-0 p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-900 transition"
							on:click={() => {
								showPreview = false;
								previewItem = null;
							}}
						>
							<XMark className="size-5" />
						</button>
					</div>
				</div>

				<div class="max-h-[75vh] overflow-auto">
					{#if loadingPreview}
						<div class="flex flex-col justify-center items-center py-12">
							<Spinner className="size-6 mb-4" />
							<div class="text-sm text-gray-500 dark:text-gray-400">
								首次预览加载可能较慢，请耐心等待。
							</div>
						</div>
					{:else if isPreviewable(previewItem)}
						{@const filename = previewItem.filename?.toLowerCase() || ''}
						{@const contentType = previewItem.meta?.content_type?.toLowerCase() || ''}
						{@const isPDF = contentType === 'application/pdf' || filename.endsWith('.pdf')}
						{@const isImage = contentType.startsWith('image/') || 
							['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].some(ext => filename.endsWith(ext))}
						{@const isText = contentType.startsWith('text/') || 
							['.txt', '.md', '.json', '.xml', '.csv', '.log'].some(ext => filename.endsWith(ext))}
						{@const isOffice = isOfficeDocument(previewItem)}

						{#if isOffice && previewUrl}
							<!-- Office 文档预览（已转换为 PDF） -->
							<iframe
								title={previewItem.filename}
								src={previewUrl}
								class="w-full h-[70vh] border-0 rounded-lg"
							></iframe>
						{:else if previewUrl}
							{#if isPDF}
								<iframe
									title={previewItem.filename}
									src={previewUrl}
									class="w-full h-[70vh] border-0 rounded-lg"
								></iframe>
							{:else if isImage}
								<div class="flex justify-center items-center">
									<img
										src={previewUrl}
										alt={previewItem.filename}
										class="max-w-full max-h-[70vh] rounded-lg"
									/>
								</div>
							{:else if isText}
								<div class="max-h-[70vh] overflow-auto">
									<iframe
										title={previewItem.filename}
										src={previewUrl}
										class="w-full h-[70vh] border-0 rounded-lg"
									></iframe>
								</div>
							{/if}
						{/if}
					{:else if !isPreviewable(previewItem)}
						<div class="flex flex-col items-center justify-center py-12">
							<div class="text-gray-500 dark:text-gray-400 text-sm mb-4">
								该文件类型不支持预览
							</div>
							<button
								class="px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-sm"
								on:click={() => downloadHandler(previewItem.id, previewItem.filename)}
							>
								下载文件
							</button>
						</div>
					{:else}
						<div class="flex flex-col items-center justify-center py-12">
							<div class="text-gray-500 dark:text-gray-400 text-sm mb-4">
								预览加载失败
							</div>
							<button
								class="px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-sm"
								on:click={() => downloadHandler(previewItem.id, previewItem.filename)}
							>
								下载文件
							</button>
						</div>
					{/if}
				</div>
			</div>
		</Modal>
	{/if}

	<!-- 上传分组选择对话框 -->
	{#if showUploadDialog}
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div
			class="fixed top-0 right-0 left-0 bottom-0 bg-black/60 w-full h-screen max-h-[100dvh] flex justify-center z-[99999999] overflow-hidden overscroll-contain"
			on:click={() => {
				showUploadDialog = false;
			}}
			role="dialog"
			aria-modal="true"
			aria-labelledby="upload-dialog-title"
			tabindex="-1"
		>
			<div
				class="m-auto max-w-full w-[32rem] mx-2 bg-white/95 dark:bg-gray-950/95 backdrop-blur-sm rounded-4xl max-h-[100dvh] shadow-3xl border border-white dark:border-gray-900 relative"
				on:click|stopPropagation
				style="overflow: visible;"
			>
				<div class="px-[1.75rem] py-6 flex flex-col">
					<div class="text-lg font-medium dark:text-gray-200 mb-4" id="upload-dialog-title">
						选择上传分组
					</div>

					<div class="text-sm text-gray-500 dark:text-gray-400 mb-4">
						请选择要将文件上传到哪个分组
					</div>

					<div class="mb-6 relative" style="z-index: 1;">
						<Select.Root
							selected={uploadGroup}
							items={uploadGroupOptions}
							onSelectedChange={(selectedItem) => {
								if (selectedItem) {
									const newGroupId = selectedItem.value || 'global';
									uploadGroupId = newGroupId;
									// 立即保存选择的分组ID
									selectedUploadGroupId = newGroupId;
									console.log('分组已选择，保存的分组ID:', selectedUploadGroupId, 'newGroupId:', newGroupId);
								}
							}}
						>
							<Select.Trigger
								class="relative w-full flex items-center gap-0.5 px-3 py-2 bg-gray-50 dark:bg-gray-850 rounded-xl"
								aria-label="选择上传分组"
							>
								<Select.Value
									class="inline-flex h-input px-0.5 w-full outline-hidden bg-transparent truncate placeholder-gray-400 focus:outline-hidden text-sm"
									placeholder="选择分组"
								/>
								<ChevronDown className="size-3.5" strokeWidth="2.5" />
							</Select.Trigger>

							<Select.Content
								class="rounded-2xl min-w-[200px] p-1 border border-gray-100 dark:border-gray-800 z-[100000000] bg-white dark:bg-gray-850 dark:text-white shadow-lg"
								sameWidth={true}
								align="start"
							>
								{#each uploadGroupOptions as item}
									<Select.Item
										class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
										value={item.value}
										label={item.label}
									>
										{item.label}

										{#if uploadGroupId === item.value}
											<div class="ml-auto">
												<Check />
											</div>
										{/if}
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>

					<div class="flex justify-between gap-1.5">
						<button
							class="text-sm bg-gray-100 hover:bg-gray-200 text-gray-800 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-white font-medium w-full py-2 rounded-3xl transition"
							on:click={() => {
								showUploadDialog = false;
							}}
							type="button"
						>
							取消
						</button>
						<button
							class="text-sm bg-gray-900 hover:bg-gray-850 text-gray-100 dark:bg-gray-100 dark:hover:bg-white dark:text-gray-800 font-medium w-full py-2 rounded-3xl transition"
							on:click={confirmUploadGroup}
							type="button"
						>
							选择文件
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}

	<div class="flex flex-col gap-1 px-1 mt-1.5 mb-3">
		<div class="flex justify-between items-center">
			<div class="flex items-center md:self-center text-xl font-medium px-0.5 gap-2 shrink-0">
				<div>共享网盘</div>
				<div class="text-lg font-medium text-gray-500 dark:text-gray-500">{total}</div>
			</div>

			<div class="flex w-full justify-end gap-1.5">
				{#if batchMode}
					<button
						class="px-2 py-1.5 rounded-xl border border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition font-medium text-sm flex items-center text-blue-600 dark:text-blue-400"
						on:click={batchSendToChat}
						disabled={selectedFileIds.size === 0}
					>
						<ChatBubble className="size-3" />
						<div class="hidden md:block md:ml-1 text-xs">发送到聊天 ({selectedFileIds.size})</div>
					</button>
					<button
						class="px-2 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition font-medium text-sm flex items-center"
						on:click={batchDownload}
						disabled={selectedFileIds.size === 0}
					>
						<Download className="size-3" />
						<div class="hidden md:block md:ml-1 text-xs">批量下载 ({selectedFileIds.size})</div>
					</button>
					<button
						class="px-2 py-1.5 rounded-xl border border-red-200 dark:border-red-800 hover:bg-red-100 dark:hover:bg-red-900/30 transition font-medium text-sm flex items-center text-red-600 dark:text-red-400"
						on:click={batchDelete}
						disabled={selectedFileIds.size === 0}
					>
						<GarbageBin className="size-3" />
						<div class="hidden md:block md:ml-1 text-xs">批量删除 ({selectedFileIds.size})</div>
					</button>
					<button
						class="px-2 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition font-medium text-sm flex items-center"
						on:click={toggleBatchMode}
					>
						<div class="text-xs">取消</div>
					</button>
				{:else}
					<button
						class="px-2 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition font-medium text-sm flex items-center"
						on:click={toggleBatchMode}
					>
						<div class="text-xs">批量操作</div>
					</button>
					<button
						class="px-2 py-1.5 rounded-xl bg-black text-white dark:bg-white dark:text-black transition font-medium text-sm flex items-center cursor-pointer {uploading
							? 'opacity-50'
							: ''}"
						on:click={openUploadDialog}
						disabled={uploading}
					>
						{#if uploading}
							<Spinner className="size-3" />
						{:else}
							<Plus className="size-3" strokeWidth="2.5" />
						{/if}
						<input
							type="file"
							bind:this={fileInput}
							class="hidden"
							multiple
							on:change={uploadHandler}
							disabled={uploading}
						/>
						<div class="hidden md:block md:ml-1 text-xs">上传文件{uploading ? '中...' : ''}</div>
					</button>
				{/if}
			</div>
		</div>

		<div
			class="py-2 bg-white dark:bg-gray-900 rounded-3xl border border-gray-100/30 dark:border-gray-850/30"
		>
			<!-- 分组筛选和搜索 -->
			<div class="flex w-full space-x-2 py-0.5 px-3.5 pb-2 gap-2">
				<!-- 分组筛选器 -->
				<div class="flex-shrink-0">
					<Select.Root
						selected={selectedGroup}
						items={groupOptions}
						onSelectedChange={(selectedItem) => {
							if (selectedItem) {
								onGroupChange(selectedItem.value);
							}
						}}
					>
						<Select.Trigger
							class="relative flex items-center gap-0.5 px-2.5 py-1.5 bg-gray-50 dark:bg-gray-850 rounded-xl min-w-[120px]"
							aria-label="选择分组"
						>
							<Select.Value
								class="inline-flex h-input px-0.5 w-full outline-hidden bg-transparent truncate placeholder-gray-400 focus:outline-hidden text-sm"
								placeholder="选择分组"
							/>
							<ChevronDown className="size-3.5" strokeWidth="2.5" />
						</Select.Trigger>

						<Select.Content
							class="rounded-2xl min-w-[170px] p-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg"
							sameWidth={false}
							align="start"
						>
							{#each groupOptions as item}
								<Select.Item
									class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
									value={item.value}
									label={item.label}
								>
									{item.label}

									{#if selectedGroupId === item.value}
										<div class="ml-auto">
											<Check />
										</div>
									{/if}
								</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>

				<!-- 搜索框 -->
				<div class="flex flex-1">
					<div class="self-center ml-1 mr-3">
						<Search className="size-3.5" />
					</div>
					<input
						class="w-full text-sm py-1 rounded-r-xl outline-hidden bg-transparent"
						bind:value={query}
						placeholder="搜索文件名"
					/>
					{#if query}
						<div class="self-center pl-1.5 translate-y-[0.5px] rounded-l-xl bg-transparent">
							<button
								class="p-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 transition"
								on:click={() => {
									query = '';
								}}
							>
								<XMark className="size-3" strokeWidth="2" />
							</button>
						</div>
					{/if}
				</div>
			</div>


			{#if loading}
				<div class="flex justify-center items-center py-8">
					<Spinner className="size-6" />
				</div>
			{:else if (files ?? []).length === 0}
				<div class="flex flex-col items-center justify-center py-12 px-4">
					<div class="text-gray-500 dark:text-gray-400 text-sm">
						暂无共享文件
					</div>
				</div>
			{:else}
				{#if batchMode}
					<div class="px-3.5 py-2 flex items-center justify-between border-b border-gray-100 dark:border-gray-800">
						<button
							class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition"
							on:click={selectAllFiles}
						>
							{#if selectedFileIds.size === files.filter((f) =>
								!query || f.filename.toLowerCase().includes(query.toLowerCase())
							).length}
								<CheckBox className="size-4 text-blue-600 dark:text-blue-400" />
							{:else}
								<!-- 空复选框 -->
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-4 text-gray-400 dark:text-gray-600"
								>
									<path
										d="M3 20.4V3.6C3 3.26863 3.26863 3 3.6 3H20.4C20.7314 3 21 3.26863 21 3.6V20.4C21 20.7314 20.7314 21 20.4 21H3.6C3.26863 21 3 20.7314 3 20.4Z"
										stroke-width="1.5"
									/>
								</svg>
							{/if}
							<span>
								{selectedFileIds.size === files.filter((f) =>
									!query || f.filename.toLowerCase().includes(query.toLowerCase())
								).length
									? '取消全选'
									: '全选'}
							</span>
						</button>
						<div class="text-sm text-gray-500 dark:text-gray-400">
							已选择 {selectedFileIds.size} 个文件
						</div>
					</div>
				{/if}
				<div class="my-2 px-3 grid grid-cols-1 lg:grid-cols-2 gap-2">
					{#each files.filter((f) =>
						!query || f.filename.toLowerCase().includes(query.toLowerCase())
					) as item}
						{@const FileIcon = getFileIcon(item)}
						{#if batchMode}
							<button
								type="button"
								class="group relative flex items-start gap-3 p-3 rounded-2xl border text-left {selectedFileIds.has(item.id)
									? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20'
									: 'border-gray-100/30 dark:border-gray-850/30 hover:border-gray-200 dark:hover:border-gray-800'} dark:bg-gray-800/50 transition cursor-pointer"
								on:click={() => toggleFileSelection(item.id)}
							>
								<!-- 复选框 -->
								<div class="flex-shrink-0 mt-0.5">
									{#if selectedFileIds.has(item.id)}
										<CheckBox className="size-4 text-blue-600 dark:text-blue-400" />
									{:else}
										<!-- 空复选框 -->
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-4 text-gray-400 dark:text-gray-600"
										>
											<path
												d="M3 20.4V3.6C3 3.26863 3.26863 3 3.6 3H20.4C20.7314 3 21 3.26863 21 3.6V20.4C21 20.7314 20.7314 21 20.4 21H3.6C3.26863 21 3 20.7314 3 20.4Z"
												stroke-width="1.5"
											/>
										</svg>
									{/if}
								</div>
								
								<!-- 文件类型图标 -->
								<div class="flex-shrink-0 mt-0.5">
									<FileIcon className="size-5 text-gray-400 dark:text-gray-500" />
								</div>
								
								<!-- 文件信息 -->
								<div class="flex-1 min-w-0">
									<div class="text-sm font-medium truncate text-gray-900 dark:text-gray-100">
										{#if query}
											{@html highlightSearchText(item.filename, query)}
										{:else}
											{item.filename}
										{/if}
									</div>
									<div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
										<span>{formatFileSize(item.meta?.size || 0)}</span>
										<span>•</span>
										<span>{formatDate(item.created_at)}</span>
									</div>
									{#if item.space_id}
										<div class="mt-1.5">
											<Badge
												content={getGroupDisplayName(item.space_id)}
												type="info"
											/>
										</div>
									{/if}
								</div>
							</button>
						{:else}
							<div
								class="group relative flex items-start gap-3 p-3 rounded-2xl border border-gray-100/30 dark:border-gray-850/30 hover:border-gray-200 dark:hover:border-gray-800 dark:bg-gray-800/50 transition"
							>
								<!-- 文件类型图标 -->
								<div class="flex-shrink-0 mt-0.5">
									<FileIcon className="size-5 text-gray-400 dark:text-gray-500" />
								</div>
								
								<!-- 文件信息 -->
								<div class="flex-1 min-w-0">
									<div class="text-sm font-medium truncate text-gray-900 dark:text-gray-100">
										{#if query}
											{@html highlightSearchText(item.filename, query)}
										{:else}
											{item.filename}
										{/if}
									</div>
									<div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
										<span>{formatFileSize(item.meta?.size || 0)}</span>
										<span>•</span>
										<span>{formatDate(item.created_at)}</span>
									</div>
									{#if item.space_id}
										<div class="mt-1.5">
											<Badge
												content={getGroupDisplayName(item.space_id)}
												type="info"
											/>
										</div>
									{/if}
								</div>
								
								<!-- 操作按钮 -->
								<div class="flex gap-1 opacity-0 group-hover:opacity-100 transition flex-shrink-0">
									{#if isPreviewable(item)}
										<button
											class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-900 transition"
											on:click={() => openPreview(item)}
											title="预览"
										>
											<Eye className="size-4 text-gray-600 dark:text-gray-400" />
										</button>
									{/if}
									<button
										class="p-1.5 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition text-blue-600 dark:text-blue-400"
										on:click={() => sendToChatHandler(item)}
										title="发送到聊天"
									>
										<ChatBubble className="size-4" />
									</button>
									<button
										class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-900 transition"
										on:click={() => downloadHandler(item.id, item.filename)}
										title="下载"
									>
										<Download className="size-4 text-gray-600 dark:text-gray-400" />
									</button>
									<button
										class="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition text-red-600 dark:text-red-400"
										on:click={() => {
											selectedItem = item;
											showDeleteConfirm = true;
										}}
										title="删除"
									>
										<GarbageBin className="size-4" />
									</button>
								</div>
							</div>
						{/if}
					{/each}
				</div>

				{#if total > pageSize}
					<div class="flex justify-center items-center gap-2 py-4">
						<button
							class="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition text-sm disabled:opacity-50"
							disabled={page === 1}
							on:click={async () => {
								page--;
								await loadFiles();
							}}
						>
							上一页
						</button>
						<div class="text-sm text-gray-500 dark:text-gray-400">
							第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页
						</div>
						<button
							class="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition text-sm disabled:opacity-50"
							disabled={page >= Math.ceil(total / pageSize)}
							on:click={async () => {
								page++;
								await loadFiles();
							}}
						>
							下一页
						</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

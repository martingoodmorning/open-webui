import { WEBUI_API_BASE_URL } from '$lib/constants';

/**
 * 获取共享文件列表
 */
export const getSharedFiles = async (
	token: string,
	page: number = 1,
	pageSize: number = 20,
	groupId?: string,
	orderBy: string = 'updated_at',
	order: 'asc' | 'desc' = 'desc',
	search?: string,
	fileType?: string,
	startDate?: number,
	endDate?: number
) => {
	let error = null;

	const params = new URLSearchParams({
		page: page.toString(),
		page_size: pageSize.toString(),
		order_by: orderBy,
		order: order
	});

	if (groupId) {
		params.append('group_id', groupId);
	}
	if (search) {
		params.append('search', search);
	}
	if (fileType) {
		params.append('file_type', fileType);
	}
	if (startDate) {
		params.append('start_date', startDate.toString());
	}
	if (endDate) {
		params.append('end_date', endDate.toString());
	}

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared?${params.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to fetch shared files';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 上传文件到共享空间
 */
export const uploadSharedFile = async (
	token: string,
	file: File,
	groupId?: string,
	metadata?: object
) => {
	let error = null;

	const formData = new FormData();
	formData.append('file', file);
	// 始终传递 group_id，即使是 'global' 也要传递
	if (groupId !== undefined && groupId !== null) {
		formData.append('group_id', groupId);
		console.log('API: 添加 group_id 到 FormData:', groupId);
	}
	if (metadata) {
		formData.append('metadata', JSON.stringify(metadata));
	}

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared`, {
		method: 'POST',
		headers: {
			authorization: `Bearer ${token}`
		},
		body: formData
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to upload file';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 下载共享文件
 */
export const downloadSharedFile = async (token: string, fileId: string, asAttachment: boolean = true) => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/files/shared/${fileId}/download?attachment=${asAttachment}`,
		{
			method: 'GET',
			headers: {
				authorization: `Bearer ${token}`
			}
		}
	);

	if (!res.ok) {
		const error = await res.json().catch(() => ({ detail: 'Failed to download file' }));
		throw error.detail || 'Failed to download file';
	}

	// 获取文件名（优先从 Content-Disposition 头获取，确保使用原文件名）
	const contentDisposition = res.headers.get('Content-Disposition');
	let filename = fileId; // 默认使用 fileId，如果无法从响应头获取
	
	if (contentDisposition) {
		// 尝试匹配 RFC5987 格式：filename*=UTF-8''encoded_filename
		// 注意：单引号在正则中需要转义，或者使用字符类
		let matches = contentDisposition.match(/filename\*=UTF-8['']([^;]+)/i);
		if (matches && matches[1]) {
			try {
				filename = decodeURIComponent(matches[1]);
			} catch (e) {
				console.warn('Failed to decode filename:', e);
			}
		} else {
			// 尝试匹配标准格式：filename="filename" 或 filename=filename
			matches = contentDisposition.match(/filename="?([^";]+)"?/i);
			if (matches && matches[1]) {
				filename = matches[1];
			}
		}
	}

	// 下载文件
	const blob = await res.blob();
	const url = window.URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename; // 使用从响应头提取的原文件名
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	window.URL.revokeObjectURL(url);
};

/**
 * 获取共享文件的预览 URL（Office 文档会转换为 PDF）
 * 优先读取缓存，不强制刷新
 */
export const getSharedFilePreviewUrl = (fileId: string) => {
	return `${WEBUI_API_BASE_URL}/files/shared/${fileId}/preview`;
};

/**
 * 删除共享文件
 */
export const deleteSharedFile = async (token: string, fileId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared/${fileId}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to delete file';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 获取共享 Excel/CSV 文件的结构预览
 */
export const getSharedExcelPreview = async (
	token: string,
	fileId: string,
	maxRows: number = 100
) => {
	let error: string | null = null;

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/files/shared/${fileId}/excel/preview?max_rows=${maxRows}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to fetch excel preview';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 根据配置获取共享 Excel/CSV 文件的图表数据
 */
export const getSharedExcelChart = async (
	token: string,
	fileId: string,
	config: any
) => {
	let error: string | null = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared/${fileId}/excel/chart`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(config)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to build excel chart';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 获取内置 Excel 图表模版列表
 */
export const getSharedExcelTemplates = async (token: string) => {
	let error: string | null = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared/excel/templates`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to fetch excel templates';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 获取某个共享文件下保存的 Excel 视图列表
 */
export const getSharedExcelViews = async (token: string, fileId: string) => {
	let error: string | null = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared/${fileId}/excel/views`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to fetch excel views';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 保存或更新 Excel 视图
 */
export const saveSharedExcelView = async (token: string, fileId: string, payload: any) => {
	let error: string | null = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/files/shared/${fileId}/excel/views`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to save excel view';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * 删除 Excel 视图
 */
export const deleteSharedExcelView = async (token: string, fileId: string, viewId: string) => {
	let error: string | null = null;

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/files/shared/${fileId}/excel/views/${viewId}`,
		{
			method: 'DELETE',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to delete excel view';
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

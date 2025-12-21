"""
字体配置工具
确保 LibreOffice 能够正确使用中文字体
"""
import os
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def ensure_chinese_fonts():
    """
    确保中文字体可用
    检查并刷新字体缓存
    """
    try:
        # 检查字体配置工具是否可用
        result = subprocess.run(
            ["which", "fc-cache"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # 刷新字体缓存
            subprocess.run(
                ["fc-cache", "-fv"],
                capture_output=True,
                timeout=30,
                check=False
            )
            log.info("Font cache refreshed")
        
        # 检查中文字体是否安装
        result = subprocess.run(
            ["fc-list", ":lang=zh"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            fonts = result.stdout.strip().split('\n')
            log.info(f"Found {len(fonts)} Chinese fonts")
            # 检查关键字体
            font_names = result.stdout.lower()
            if 'wqy' in font_names or 'noto' in font_names or 'source han' in font_names:
                log.info("Chinese fonts are available")
                return True
            else:
                log.warning("Chinese fonts may not be properly installed")
                return False
        else:
            log.warning("No Chinese fonts found")
            return False
            
    except Exception as e:
        log.warning(f"Error checking fonts: {str(e)}")
        return False


def get_font_env():
    """
    获取配置了中文字体的环境变量
    """
    env = os.environ.copy()
    env['LANG'] = 'zh_CN.UTF-8'
    env['LC_ALL'] = 'zh_CN.UTF-8'
    env['LANGUAGE'] = 'zh_CN:zh:en_US:en'
    
    # 设置字体配置路径
    if Path('/etc/fonts/fonts.conf').exists():
        env['FONTCONFIG_FILE'] = '/etc/fonts/fonts.conf'
    
    # 设置 LibreOffice 的字体路径
    # LibreOffice 使用自己的字体配置
    libreoffice_font_paths = [
        '/usr/share/fonts',
        '/usr/local/share/fonts',
        '/home/.fonts',
    ]
    
    # 确保 LibreOffice 能找到字体
    for font_path in libreoffice_font_paths:
        if Path(font_path).exists():
            env.setdefault('FONTPATH', '')
            if font_path not in env['FONTPATH']:
                env['FONTPATH'] = f"{env['FONTPATH']}:{font_path}".lstrip(':')
    
    return env


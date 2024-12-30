from fastapi import FastAPI, HTTPException
import httpx
from magic_html import GeneralExtractor
from typing import Optional, Literal
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import re
import chardet

app = FastAPI()
extractor = GeneralExtractor()

async def fetch_url(url: str) -> str:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            # 首先尝试从响应头获取编码
            content_type = response.headers.get('content-type', '').lower()
            if 'charset=' in content_type:
                try:
                    # 从Content-Type中提取charset
                    charset = content_type.split('charset=')[-1].split(';')[0]
                    return response.content.decode(charset)
                except:
                    pass
            
            # 如果响应头中没有编码信息，或解码失败，尝试直接解码
            try:
                return response.content.decode('utf-8')
            except UnicodeDecodeError:
                # 如果UTF-8解码失败，尝试检测编码
                content = response.content
                detected = chardet.detect(content)
                encoding = detected['encoding']
                
                # 如果是GB2312或GBK，使用GB18030
                if encoding and encoding.lower() in ['gb2312', 'gbk']:
                    encoding = 'gb18030'
                
                # 使用检测到的编码解码内容
                return content.decode(encoding or 'utf-8')
            
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error fetching URL: {str(e)}")

def clean_markdown(text: str) -> str:
    """
    清理和优化markdown文本
    
    Args:
        text: 原始markdown文本
        
    Returns:
        清理后的markdown文本
    """
    # 移除多余的空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 移除行首尾的空格
    text = '\n'.join(line.strip() for line in text.split('\n'))
    # 移除不必要的标记符号
    text = re.sub(r'={3,}', '', text)
    # 优化图片链接格式
    text = re.sub(r'!\[\]\((.*?)\)', r'![图片](\1)', text)
    return text.strip()

def convert_content(html: str, output_format: str) -> str:
    """
    将HTML内容转换为指定格式
    
    Args:
        html: HTML内容
        output_format: 输出格式 ("html", "markdown", "text")
        
    Returns:
        转换后的内容
    """
    if not isinstance(html, str):
        html = str(html)
        
    if output_format == "html":
        return html
    elif output_format == "markdown":
        markdown = md(html)
        return clean_markdown(markdown)
    elif output_format == "text":
        soup = BeautifulSoup(html, 'html.parser')
        return soup.get_text(separator='\n', strip=True)
    else:
        return html

def extract_html_content(data: dict) -> str:
    """
    从magic_html返回的数据中提取HTML内容
    
    Args:
        data: magic_html返回的数据
        
    Returns:
        HTML内容
    """
    if isinstance(data, dict):
        return data.get('html', '')
    return ''

def detect_html_type(html: str, url: str) -> str:
    """
    自动检测HTML类型
    
    Args:
        html: HTML内容
        url: 页面URL
        
    Returns:
        检测到的类型 ("article", "forum", "weixin")
    """
    # 检查URL特征
    url_lower = url.lower()
    if any(domain in url_lower for domain in ['mp.weixin.qq.com', 'weixin.qq.com']):
        return 'weixin'
    
    # 检查HTML特征
    soup = BeautifulSoup(html, 'html.parser')
    
    # 论坛特征检测
    forum_indicators = [
        'forum', 'topic', 'thread', 'post', 'reply', 'comment', 'discuss',
        '论坛', '帖子', '回复', '评论', '讨论'
    ]
    
    # 检查类名和ID
    classes_and_ids = []
    for element in soup.find_all(class_=True):
        classes_and_ids.extend(element.get('class', []))
    for element in soup.find_all(id=True):
        classes_and_ids.append(element.get('id', ''))
    
    classes_and_ids = ' '.join(classes_and_ids).lower()
    
    if any(indicator in classes_and_ids for indicator in forum_indicators):
        return 'forum'
    
    # 默认为文章类型
    return 'article'

@app.get("/api/extract")
async def extract_content(
    url: str, 
    output_format: Optional[Literal["html", "markdown", "text"]] = "text"
):
    """
    从URL提取内容
    
    Args:
        url: 目标网页URL
        output_format: 输出格式 ("html", "markdown", "text")，默认为text
    
    Returns:
        JSON格式的提取内容
    """
    try:
        html = await fetch_url(url)
        
        # 自动检测HTML类型
        html_type = detect_html_type(html, url)
        
        extracted_data = extractor.extract(html, base_url=url, html_type=html_type)
        
        # 从返回数据中提取HTML内容
        html_content = extract_html_content(extracted_data)
        
        # 转换内容格式
        converted_content = convert_content(html_content, output_format)
        
        return {
            "url": url,
            "content": converted_content,
            "format": output_format,
            "type": html_type,  # 返回检测到的类型
            "success": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 
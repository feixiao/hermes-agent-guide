#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Agent 白皮书 —— EPUB 导出生成脚本
用法:
    pip install markdown ebooklib
    python generate_epub.py

或使用 uv:
    uv run --with markdown --with ebooklib python3 generate_epub.py
"""

import os
import sys
import re
import uuid
from pathlib import Path

try:
    import markdown
except ImportError:
    print("❌ 错误: 缺少 markdown 库。请执行: pip install markdown")
    sys.exit(1)

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    print("❌ 错误: 缺少 ebooklib 库。请执行: pip install ebooklib")
    sys.exit(1)


VALID_HTML_TAGS = {
    'a', 'abbr', 'address', 'area', 'article', 'aside', 'audio', 'b', 'base', 'bdi',
    'bdo', 'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'cite', 'code',
    'col', 'colgroup', 'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog',
    'div', 'dl', 'dt', 'em', 'embed', 'fieldset', 'figcaption', 'figure', 'footer',
    'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html', 'i',
    'iframe', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'link', 'main',
    'map', 'mark', 'meta', 'meter', 'nav', 'noscript', 'object', 'ol', 'optgroup',
    'option', 'output', 'p', 'param', 'picture', 'pre', 'progress', 'q', 'rb', 'rp',
    'rt', 'rtc', 'ruby', 's', 'samp', 'script', 'section', 'select', 'small', 'source',
    'span', 'strong', 'style', 'sub', 'summary', 'sup', 'svg', 'table', 'tbody', 'td',
    'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track',
    'u', 'ul', 'var', 'video', 'wbr'
}


def get_md_files(directory):
    """按编号顺序获取所有 Markdown 分册文件"""
    md_files = sorted(
        [f for f in os.listdir(directory) if f.endswith('.md') and re.match(r'^\d{2}-', f)],
        key=lambda x: int(re.match(r'^(\d+)', x).group(1))
    )
    return md_files


def escape_non_html_tags(text):
    """
    转义 Markdown 中作者书写的占位符标签（例如 <Topic>, <Point 1>, <YOUR_KEY> 等），
    防止其被解析为非法 XHTML 标签而破坏 EPUB 结构。
    """
    def repl(m):
        full = m.group(0)
        tag_name = m.group(1).lower()
        if tag_name in VALID_HTML_TAGS:
            return full
        return full.replace('<', '&lt;').replace('>', '&gt;')

    return re.sub(r'</?([a-zA-Z0-9_\-]+)(?:\s+[^>]*)?/?>', repl, text)


def clean_markdown_content(content):
    """清理多余的分页符和封面占位 HTML"""
    # 移除 HTML 封面 div（EPUB 会以原生 cover 机制展示）
    content = re.sub(r'<div class="cover-page">[\s\S]*?</div>', '', content, flags=re.IGNORECASE)
    # 移除分页符 div
    content = re.sub(r'<div class="page-break">\s*</div>', '', content, flags=re.IGNORECASE)
    # 转义非 HTML 标签的尖括号占位符
    content = escape_non_html_tags(content)
    return content.strip()


def render_markdown_to_html(md_content):
    """渲染 Markdown 为标准 XHTML"""
    extensions = [
        'markdown.extensions.tables',
        'markdown.extensions.fenced_code',
        'markdown.extensions.sane_lists',
        'markdown.extensions.smarty',
    ]

    try:
        import pymdownx
        extensions.extend([
            'pymdownx.superfences',
            'pymdownx.highlight',
            'pymdownx.inlinehilite',
            'pymdownx.details',
            'pymdownx.tabbed',
            'pymdownx.tasklist',
            'pymdownx.keys',
        ])
    except ImportError:
        pass

    md = markdown.Markdown(extensions=extensions, output_format='xhtml')
    return md.convert(md_content)


def post_process_html(html_body):
    """为引用提示框添加语义化样式类名"""
    patterns = [
        (r'<blockquote>\s*<p><strong>Tips</strong>', '<blockquote class="tip"><p><strong>Tips</strong>'),
        (r'<blockquote>\s*<p><strong>注意</strong>', '<blockquote class="warning"><p><strong>注意</strong>'),
        (r'<blockquote>\s*<p><strong>警告</strong>', '<blockquote class="danger"><p><strong>警告</strong>'),
        (r'<blockquote>\s*<p><strong>常见问题</strong>', '<blockquote class="faq"><p><strong>常见问题</strong>'),
        (r'<blockquote>\s*<p><strong>本章你将学到</strong>', '<blockquote class="learn"><p><strong>本章你将学到</strong>'),
    ]
    for pattern, replacement in patterns:
        html_body = re.sub(pattern, replacement, html_body, flags=re.IGNORECASE)
    return html_body


def extract_sections_and_inject_ids(html_content, file_prefix):
    """
    提取 H2 标题构建二级目录，并为没有 id 的 H2 注入锚点 id。
    返回修改后的 HTML 与 (title, anchor_id) 列表。
    """
    sections = []
    sec_counter = 0

    def replace_h2(match):
        nonlocal sec_counter
        attrs = match.group(1) or ""
        text = match.group(2)
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        sec_counter += 1

        id_match = re.search(r'id=["\']([^"\']+)["\']', attrs)
        if id_match:
            sec_id = id_match.group(1)
        else:
            sec_id = f"{file_prefix}-sec-{sec_counter}"
            attrs = f'{attrs} id="{sec_id}"'.strip()

        sections.append((clean_text, sec_id))
        return f'<h2 {attrs}>{text}</h2>'

    modified_html = re.sub(r'<h2([^>]*)>(.*?)</h2>', replace_h2, html_content, flags=re.DOTALL)
    return modified_html, sections


def build_epub_css():
    """电子书排版 CSS 样式，适配各种阅读器与深浅色模式"""
    return '''@charset "utf-8";

/* 正文基础排版 */
body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", sans-serif;
    font-size: 1em;
    line-height: 1.8;
    color: #2c3e50;
    margin: 0;
    padding: 0 4%;
    text-align: justify;
}

/* 标题样式 */
h1 {
    font-size: 1.6em;
    font-weight: bold;
    color: #1a1a1a;
    margin-top: 1.2em;
    margin-bottom: 0.8em;
    padding-bottom: 0.3em;
    border-bottom: 2px solid #e74c3c;
    line-height: 1.3;
}

h2 {
    font-size: 1.3em;
    font-weight: bold;
    color: #2c3e50;
    margin-top: 1.5em;
    margin-bottom: 0.6em;
    padding-bottom: 0.2em;
    border-bottom: 1px solid #eaecef;
    line-height: 1.3;
}

h3 {
    font-size: 1.15em;
    font-weight: bold;
    color: #34495e;
    margin-top: 1.2em;
    margin-bottom: 0.5em;
    line-height: 1.3;
}

h4 {
    font-size: 1.05em;
    font-weight: bold;
    color: #4f5f6f;
    margin-top: 1em;
    margin-bottom: 0.4em;
}

/* 段落与文字 */
p {
    margin: 0.8em 0;
    line-height: 1.8;
}

strong {
    font-weight: bold;
    color: #111;
}

a {
    color: #2980b9;
    text-decoration: none;
}

/* 列表 */
ul, ol {
    padding-left: 1.6em;
    margin: 0.8em 0;
}

li {
    margin: 0.4em 0;
    line-height: 1.7;
}

/* 提示框 / 引用块 */
blockquote {
    margin: 1.2em 0;
    padding: 0.8em 1.2em;
    border-left: 4px solid #7f8c8d;
    background-color: #f8f9fa;
    border-radius: 0 4px 4px 0;
}

blockquote p {
    margin: 0.4em 0;
}

blockquote.tip {
    border-left-color: #3498db;
    background-color: #f0f7ff;
}

blockquote.warning {
    border-left-color: #e67e22;
    background-color: #fff8f0;
}

blockquote.danger {
    border-left-color: #e74c3c;
    background-color: #fdf2f2;
}

blockquote.faq {
    border-left-color: #27ae60;
    background-color: #f0fff4;
}

blockquote.learn {
    border-left-color: #9b59b6;
    background-color: #f9f0ff;
}

/* 行内代码与代码块 */
code {
    font-family: "SF Mono", "Fira Code", Consolas, Monaco, "Courier New", monospace;
    font-size: 0.88em;
    background-color: #f1f3f4;
    color: #c7254e;
    padding: 2px 5px;
    border-radius: 3px;
}

pre {
    background-color: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-left: 4px solid #0366d6;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin: 1.2em 0;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

pre code {
    background-color: transparent;
    color: #24292e;
    padding: 0;
    font-size: 0.85em;
    border-radius: 0;
}

/* 表格 */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.2em 0;
    font-size: 0.88em;
}

th {
    background-color: #f1f4f8;
    color: #24292e;
    font-weight: bold;
    padding: 8px 10px;
    border: 1px solid #d0d7de;
    text-align: left;
}

td {
    padding: 8px 10px;
    border: 1px solid #d0d7de;
    vertical-align: top;
}

tr:nth-child(even) {
    background-color: #f9fafb;
}

/* 分隔线与图片 */
hr {
    border: 0;
    height: 1px;
    background-color: #e1e4e8;
    margin: 1.8em 0;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}
'''


def generate_epub(input_dir=None, output_path=None):
    if input_dir is None:
        input_dir = os.path.dirname(os.path.abspath(__file__))
    if output_path is None:
        output_path = os.path.join(input_dir, "Hermes-Agent白皮书-养马从入门到精通-鲲鹏Talk.epub")

    print(f"📖 工作目录: {input_dir}")

    # 1. 初始化电子书
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title("Hermes Agent 白皮书 —— 养马从入门到精通")
    book.set_language("zh-CN")
    book.add_author("鲲鹏Talk")
    book.add_metadata('DC', 'description', '开源社区第一本系统性 Hermes Agent 中文指南')
    book.add_metadata('DC', 'publisher', '鲲鹏Talk')

    # 2. 加载封面
    cover_path = os.path.join(input_dir, "封面.png")
    if os.path.exists(cover_path):
        print(f"🖼️  加载封面: {cover_path}")
        with open(cover_path, "rb") as f:
            book.set_cover("cover.png", f.read())
    else:
        print("⚠️ 未找到 封面.png，将不包含封面图")

    # 3. 注入样式表
    css_content = build_epub_css()
    book_css = epub.EpubItem(
        uid="book_style",
        file_name="style/book.css",
        media_type="text/css",
        content=css_content
    )
    book.add_item(book_css)

    # 4. 读取分册文件
    md_files = get_md_files(input_dir)
    print(f"📚 找到 {len(md_files)} 个分册 Markdown 文件")

    chapters = []
    toc_structure = []

    for idx, md_file in enumerate(md_files):
        file_path = os.path.join(input_dir, md_file)
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        clean_md = clean_markdown_content(raw_content)

        # 提取标题
        title_match = re.search(r'^#\s+(.+)$', clean_md, re.MULTILINE)
        if title_match:
            chapter_title = title_match.group(1).strip()
        else:
            chapter_title = md_file.replace('.md', '')

        # 渲染与后处理
        html_body = render_markdown_to_html(clean_md)
        html_body = post_process_html(html_body)

        # 注入小节锚点
        chap_slug = f"chap_{idx:02d}"
        file_name = f"{chap_slug}.xhtml"
        html_body, sections = extract_sections_and_inject_ids(html_body, chap_slug)

        # 组合完整 XHTML
        full_xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
<head>
    <meta charset="utf-8"/>
    <title>{chapter_title}</title>
    <link rel="stylesheet" type="text/css" href="style/book.css"/>
</head>
<body>
{html_body}
</body>
</html>'''

        chapter_item = epub.EpubHtml(
            title=chapter_title,
            file_name=file_name,
            lang="zh-CN"
        )
        chapter_item.content = full_xhtml.encode('utf-8')
        chapter_item.add_item(book_css)

        book.add_item(chapter_item)
        chapters.append(chapter_item)

        # 构建目录层级 (H1 -> H2)
        if sections:
            sec_links = [
                epub.Link(f"{file_name}#{sec_id}", sec_title, f"{chap_slug}_{s_idx}")
                for s_idx, (sec_title, sec_id) in enumerate(sections)
            ]
            toc_structure.append((epub.Section(chapter_title, href=file_name), sec_links))
        else:
            toc_structure.append(chapter_item)

        print(f"  ✓ [{idx+1}/{len(md_files)}] {md_file} -> {chapter_title} ({len(sections)} 个小节)")

    # 5. 组装导航与阅读流
    book.toc = toc_structure
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters

    # 6. 生成并写出 EPUB 文件
    print(f"\n📦 正在生成 EPUB 文件: {output_path} ...")
    epub.write_epub(output_path, book, {})

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"🎉 导出完成！文件大小: {file_size_mb:.2f} MB")
    return output_path


if __name__ == '__main__':
    generate_epub()

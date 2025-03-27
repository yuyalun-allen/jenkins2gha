import re


def extract_block(content: str, block_name: str) -> str:
    """
    提取指定名称的块内容，处理嵌套的大括号。
    """
    pattern = re.compile(rf'{block_name}\s*\{{')
    match = pattern.search(content)
    if not match:
        return ""

    start = match.end()
    brace_count = 1
    index = start
    while index < len(content) and brace_count > 0:
        if content[index] == '{':
            brace_count += 1
        elif content[index] == '}':
            brace_count -= 1
        index += 1

    return content[start:index - 1].strip()  # 去除结尾的 '}'

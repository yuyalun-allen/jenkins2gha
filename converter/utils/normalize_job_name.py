import re


def normalize_identifier(target_str):
    """
    将目标字符串转换为符合命名规范的字符串：
    1. 必须以字母或下划线开头
    2. 只能包含字母数字字符、连字符或下划线

    参数:
        target_str (str): 需要规范化的字符串

    返回:
        str: 符合命名规范的字符串
    """
    if not target_str:
        return "_"

    # 第一步：替换所有非允许字符为下划线
    normalized = re.sub(r'[^a-zA-Z0-9_-]', '_', target_str)

    # 第二步：确保首字符是字母或下划线
    if not re.match(r'^[a-zA-Z_]', normalized):
        normalized = '_' + normalized

    return normalized



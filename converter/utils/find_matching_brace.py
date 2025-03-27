def find_matching_brace(text, start_pos):
    """
    找到与给定位置的左大括号匹配的右大括号。
    处理嵌套大括号的情况。
    """
    stack = 0
    for i in range(start_pos, len(text)):
        if text[i] == '{':
            stack += 1
        elif text[i] == '}':
            stack -= 1
            if stack == 0:
                return i
    return -1  # 没有找到匹配的右大括号

from converter.utils.getLogger import setup_logging

logger = setup_logging()


def remove_groovy_comments(file_content: str) -> str:
    """
    通过手动状态机方式，去除单行和多行注释，同时保留字符串字面量里的内容。

    1. 单行注释: 以 // 开头，但如果出现于字符串中 (单引号/双引号) 则视为普通文本。
    2. 多行注释: /* ... */，同样若出现在字符串中则忽略。
    3. 字符串: 支持单引号与双引号，但不处理三引号这种更复杂的情况。

    :param file_content: 原始 Jenkinsfile.groovy (Groovy) 文件内容
    :return: 去掉注释后的文件内容
    """

    result = []
    length = len(file_content)
    i = 0

    # 状态标识
    in_single_quote = False   # 是否在单引号字符串中
    in_double_quote = False   # 是否在双引号字符串中
    in_block_comment = False  # 是否在多行注释中

    while i < length:
        char = file_content[i]

        # 检查多行注释结束
        if in_block_comment:
            # 如果遇到 "*/" 则关闭多行注释
            if char == '*' and i + 1 < length and file_content[i+1] == '/':
                in_block_comment = False
                i += 2  # 跳过 "*/"
            else:
                i += 1  # 继续跳过注释内容
            continue

        # 如果不在多行注释中，先检查是否在字符串里
        if in_single_quote:
            # 检测单引号结束
            if char == "'" and not is_escaped(file_content, i):
                in_single_quote = False
            # 无论是什么，都要把字符加进去
            result.append(char)
            i += 1
            continue

        if in_double_quote:
            # 检测双引号结束
            if char == '"' and not is_escaped(file_content, i):
                in_double_quote = False
            result.append(char)
            i += 1
            continue

        # 如果当前既不在字符串，也不在多行注释里，检查注释或字符串起始
        if char == '/':
            # 1) 可能是单行注释 "//"
            if i + 1 < length and file_content[i+1] == '/':
                # 跳过单行注释直到换行符或文件末尾
                i += 2
                while i < length and file_content[i] not in ('\n', '\r'):
                    i += 1
                continue

            # 2) 可能是多行注释 "/*"
            if i + 1 < length and file_content[i+1] == '*':
                in_block_comment = True
                i += 2
                continue

            # 否则就只是普通的 '/'
            result.append(char)
            i += 1
            continue

        # 检查是否遇到引号开始：单引号 or 双引号
        if char == "'":
            in_single_quote = True
            result.append(char)
            i += 1
            continue

        if char == '"':
            in_double_quote = True
            result.append(char)
            i += 1
            continue

        # 普通字符，直接加入
        result.append(char)
        i += 1

    logger.info(f"Remove_groovy_comments: Removed file='{''.join(result)}'")
    return ''.join(result)


def is_escaped(text: str, pos: int) -> bool:
    """
    判断当前位置的引号是否被转义(例如 '\\' + 引号)。
    若前面是偶数个反斜杠，则未被转义；若是奇数个反斜杠，则被转义。
    """
    backslash_count = 0
    # 逆向统计连续的 '\\'
    idx = pos - 1
    while idx >= 0 and text[idx] == '\\':
        backslash_count += 1
        idx -= 1
    # 如果反斜杠的数量是奇数，说明当前引号被转义
    return (backslash_count % 2) == 1

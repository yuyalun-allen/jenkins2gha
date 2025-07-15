import re
from typing import List, Dict, Any
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def split_steps_content(steps_content: str) -> List[str]:
    """
    将 steps_content 分割成独立的步骤单元，保持顺序。
    基于Jenkins DSL语法模式进行分析，而不依赖特定步骤名称的枚举。
    """
    if not steps_content.strip():
        return []

    lines = steps_content.split('\n')
    steps = []
    line_index = 0

    while line_index < len(lines):
        # 跳过空行
        while line_index < len(lines) and not lines[line_index].strip():
            line_index += 1

        if line_index >= len(lines):
            break

        # 开始一个新步骤
        step_start_index = line_index

        # 语法状态跟踪
        brace_level = 0  # 花括号 { }
        paren_level = 0  # 小括号 ( )
        bracket_level = 0  # 方括号 [ ]
        in_string = False
        string_char = None
        escaped = False

        # 识别步骤类型和结构
        current_line = lines[line_index].strip()
        step_type = identify_step_type(current_line)
        step_complete = False

        # 处理当前行及后续行，直到步骤完成
        while line_index < len(lines):
            current_line = lines[line_index]
            stripped_line = current_line.strip()

            # 跳过空行和注释行
            if not stripped_line or stripped_line.startswith('//') or stripped_line.startswith('#'):
                line_index += 1
                continue

            # 检查这行是否开始一个新的步骤（当前步骤已完成）
            # 只有当我们不在代码块、字符串或括号内部时才考虑
            if step_start_index != line_index:  # 不检查第一行
                if brace_level == 0 and paren_level == 0 and bracket_level == 0 and not in_string:
                    # 识别新行的类型
                    new_line_type = identify_step_type(stripped_line)

                    # 如果新行是一个完整的语法单元，可能是新步骤的开始
                    if new_line_type in ["STATEMENT", "METHOD_CALL", "FUNCTION_CALL", "VARIABLE_DEFINITION",
                                         "CODE_BLOCK"] and not is_continuation_line(stripped_line):
                        break

            # 分析当前行的语法结构
            i = 0
            while i < len(stripped_line):
                char = stripped_line[i]

                # 处理转义字符
                if escaped:
                    escaped = False
                    i += 1
                    continue

                if char == '\\':
                    escaped = True
                    i += 1
                    continue

                # 处理字符串
                if in_string:
                    if char == string_char and not escaped:
                        in_string = False
                        string_char = None
                    i += 1
                    continue

                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    i += 1
                    continue

                # 处理括号
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                    # 检查代码块是否已完成
                    if brace_level == 0 and step_type == "CODE_BLOCK":
                        step_complete = True
                elif char == '(':
                    paren_level += 1
                elif char == ')':
                    paren_level -= 1
                    # 检查函数调用是否已完成
                    if paren_level == 0 and step_type in ["FUNCTION_CALL", "METHOD_CALL"] and ';' in stripped_line[i:]:
                        step_complete = True
                elif char == '[':
                    bracket_level += 1
                elif char == ']':
                    bracket_level -= 1

                # 检查语句结束符
                if not in_string and char == ';' and brace_level == 0 and paren_level == 0 and bracket_level == 0:
                    step_complete = True

                i += 1

            # 记录当前行并前进
            line_index += 1

            # 检查步骤是否完成
            if step_complete:
                break

            # 如果所有括号都已闭合，检查是否可能是简单语句的结束
            if brace_level == 0 and paren_level == 0 and bracket_level == 0 and not in_string:
                # 如果是简单语句且不以逗号或反斜杠结束，可能已经完成
                if step_type == "STATEMENT" and not stripped_line.endswith(',') and not stripped_line.endswith('\\'):
                    break

        # 提取步骤内容
        step_lines = lines[step_start_index:line_index]
        step_text = '\n'.join(step_lines).strip()

        # 只有当步骤内容不为空时才添加
        if step_text:
            steps.append(step_text)

    return steps


def identify_step_type(line):
    """
    基于语法模式识别行的类型，不依赖特定步骤名称。
    """
    line = line.strip()
    if not line:
        return "EMPTY"

    # 注释
    if line.startswith('//') or line.startswith('#'):
        return "COMMENT"

    # 变量定义
    if line.startswith('def ') or ('=' in line and not line.strip().startswith('=')):
        return "VARIABLE_DEFINITION"

    # 方法调用 (带点号)
    if '.' in line.split()[0]:
        return "METHOD_CALL"

    # 包含花括号的代码块，适用于任何格式的代码块，包括script块
    if '{' in line or line.strip().endswith('{'):
        return "CODE_BLOCK"

    # 函数调用 (通常以标识符开头，可能后跟括号或参数)
    first_word = line.split()[0]
    if first_word.isalpha() and (
            '(' in line or
            any(line.strip().startswith(w) for w in ['sh ', 'echo ']) or
            (':' in line and not line.startswith(':'))
    ):
        return "FUNCTION_CALL"

    # 默认为简单语句
    return "STATEMENT"


def is_continuation_line(line):
    """
    检查一行是否是前一行的延续，基于语法特征而不是特定关键字。
    """
    line = line.strip()

    # 参数行通常以标识符加冒号开头
    if re.match(r'^\w+:\s', line):
        return True

    # 以逗号开头的行
    if line.startswith(','):
        return True

    # 以闭合括号开头的行，可能是前一行结构的结束
    if line.startswith(')') or line.startswith('}') or line.startswith(']'):
        return True

    return False

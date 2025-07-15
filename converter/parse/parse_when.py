import re
from typing import Dict, Any, List, Optional, Tuple
from converter.utils.getLogger import setup_logging
from converter.utils.extract_block_by_scope import extract_block_by_scope

logger = setup_logging()


# ---------------------------------------------------------------------
# 1) 先写一个“解析 when 块”的入口方法
# ---------------------------------------------------------------------
def parse_when_block(stage_content: str) -> Optional[str]:
    """
    从单个 stage 的内容中，提取 when { ... } 并解析所有条件，
    最终返回一个适合 GitHub Actions 的表达式字符串(不含 if: ${{ }} 这部分)。

    如果没有 when 块，则返回 None。
    """
    when_content = extract_block_by_scope(stage_content, 'when', scope='stage')
    if not when_content:
        logger.info("No 'when' block found in this stage.")
        return None

    logger.info(f"Found when block: {when_content}")

    # 调用递归解析入口，把 when_content 转成条件表达式树
    condition_expr = parse_when_conditions(when_content)

    logger.info(f"Converted Jenkins 'when' => GHA expression: {condition_expr}")
    return condition_expr


# ---------------------------------------------------------------------
# 2) 解析 when { ... } 里的条件内容
#    - 可能会包含 multiple lines, allOf, anyOf, not
#    - 逐行或者递归方式解析
# ---------------------------------------------------------------------
def parse_when_conditions(when_block_content: str) -> str:
    """
    解析 when { ... } 块内部的多行条件，并将它们组合成
    GitHub Actions 的表达式字符串(仅表达式部分)。

    Jenkins 默认多个条件并列时，相当于 allOf。
    如果显式出现 anyOf 或 not，则需要递归处理子条件。
    """
    # 1) 如果出现 allOf / anyOf / not 这样的嵌套结构，要优先做递归
    #    由于 Jenkins 里它们也写在 when { } 之内，需要先检测并解析之。
    #    这里做一个简易处理：如果匹配到 `allOf { ... }`，调用 parse_sub_block(...)
    #    anyOf、not 同理。
    #    若没有匹配到嵌套结构，再逐行解析普通条件。
    nested_allof_matches = re.search(r'allOf\s*\{', when_block_content)
    nested_anyof_matches = re.search(r'anyOf\s*\{', when_block_content)
    nested_not_matches = re.search(r'not\s*\{', when_block_content)

    if nested_allof_matches or nested_anyof_matches or nested_not_matches:
        # 存在嵌套结构 => 可能是一大坨
        # 简化做法：把 top-level 的多个子块解析，然后再合并
        # 这里直接做一个“全量拆分子块”方法
        sub_conditions = extract_nested_when_clauses(when_block_content)
        # sub_conditions 将是 [("allOf", "内部文本"), ("environment", "内部文本"), ...] 这样的列表
        # 下面把它们逐个解析
        parsed_parts = []
        for cond_type, cond_body in sub_conditions:
            expr = parse_single_condition(cond_type, cond_body)
            parsed_parts.append(expr)

        # Jenkins if 同级多条件 => allOf
        if len(parsed_parts) > 1:
            return ' && '.join(f'({p})' for p in parsed_parts)
        else:
            return parsed_parts[0] if parsed_parts else ""

    else:
        # 2) 如果没有嵌套结构，就按“多行条件 => allOf”处理
        lines = [l.strip() for l in when_block_content.split('\n') if l.strip()]
        # 过滤掉最外层可能的花括号
        lines = [re.sub(r'^\{|\}$', '', line) for line in lines]
        lines = [l for l in lines if l]

        parsed_parts = []
        for line in lines:
            cond_type, cond_body = split_condition_line(line)
            expr = parse_single_condition(cond_type, cond_body)
            if expr:
                parsed_parts.append(expr)

        if not parsed_parts:
            return ""
        if len(parsed_parts) == 1:
            return parsed_parts[0]
        return ' && '.join(f'({p})' for p in parsed_parts)


# ---------------------------------------------------------------------
# 3) 解析单个 condition：branch, environment, not, anyOf, etc.
#    这个函数只返回表达式字符串，如 "github.ref == 'refs/heads/main'"
# ---------------------------------------------------------------------
def parse_single_condition(cond_type: str, cond_body: str) -> str:
    """
    根据 condition 类型（branch / environment / allOf / anyOf / not / 等）,
    返回 GitHub Actions expression string.

    cond_body 可能是 "'main'", 或者 "name: 'DEPLOY_TO', value: 'production'"
    或者更复杂的子块。
    """
    cond_type = cond_type.strip()
    cond_body = cond_body.strip()

    # 先处理三大逻辑组合：allOf, anyOf, not
    if cond_type == "allOf":
        # 递归解析 cond_body 里的若干子条件
        sub_expr = parse_when_conditions(cond_body)
        return sub_expr  # allOf => 全部 &&, parse_when_conditions里会给出
    elif cond_type == "anyOf":
        # anyOf => 多个子条件或关系
        sub_conditions = extract_nested_when_clauses(cond_body)
        # sub_conditions = [(cond_type, cond_block), ...]
        parsed_parts = []
        for t, b in sub_conditions:
            parsed_parts.append(parse_single_condition(t, b))
        return ' || '.join(f'({p})' for p in parsed_parts if p)
    elif cond_type == "not":
        # not => 取反
        sub_conditions = extract_nested_when_clauses(cond_body)
        # 一般 only one inside not
        if not sub_conditions:
            return ""
        t, b = sub_conditions[0]  # 只取第一个
        return f'!({parse_single_condition(t, b)})'

    # 处理常见内置条件
    if cond_type.startswith("branch"):
        # branch 'main'
        # 可能写作: branch pattern: "release-*", comparator: "GLOB"
        # 简化: 只抓最常见写法 branch 'xxx'
        pattern = get_quoted_string(cond_body)
        if not pattern:
            return ""  # 解析失败
        # GH Actions: if: ${{ github.ref == 'refs/heads/main' }}
        return f'github.ref == "refs/heads/{pattern}"'
    elif cond_type.startswith("environment"):
        # environment name: 'DEPLOY_TO', value: 'production'
        # 简化匹配: name: 'DEPLOY_TO', value: 'production'
        m = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"].*value\s*:\s*['\"]([^'\"]+)['\"]", cond_body)
        if not m:
            return ""
        env_name, env_value = m.groups()
        return f'env.{env_name} == "{env_value}"'
    elif cond_type.startswith("buildingTag"):
        # buildingTag()
        # GH Actions: if: ${{ startsWith(github.ref, 'refs/tags/') }}
        return 'startsWith(github.ref, "refs/tags/")'
    elif cond_type.startswith("tag"):
        # tag "release-*"
        # 暂时简化 => if: ${{ startsWith(github.ref, 'refs/tags/release-') }}
        pattern = get_quoted_string(cond_body)
        if not pattern:
            # 空pattern => buildingTag() 类似
            return 'startsWith(github.ref, "refs/tags/")'
        # 不细做 GLOB => 只给一个 placeholder
        return f'startsWith(github.ref, "refs/tags/") /* matches {pattern} */'
    elif cond_type.startswith("expression"):
        # expression { return params.DEBUG_BUILD }
        # 在 Jenkins 里是个 Groovy 表达式，转换很难一一对应
        # 简化：把它当成 "true" or "false" 占位
        return '(/* Jenkins expression not directly translatable */ false)'
    else:
        # 其它常见的: changelog, changeset, changeRequest, triggeredBy, equals...
        # 这里演示做一个 placeholder
        return f'(/* Unsupported condition: {cond_type} */ false)'


# ---------------------------------------------------------------------
# 4) 提取嵌套子条件，用于处理 allOf { ... }, anyOf { ... }, not { ... } 的递归
#    返回类似: [("branch","'main'"), ("environment","name: 'DEPLOY_TO'..."), ...]
# ---------------------------------------------------------------------
def extract_nested_when_clauses(block_content: str) -> List[Tuple[str, str]]:
    """
    扫描 block_content 内部，找出形如  allOf { ... }, anyOf { ... }, not { ... }
    以及普通内置条件( branch 'xxx', environment name: 'xxx', ... )。
    并把它们分割成若干 (cond_type, cond_body) 项返回。

    例如：如果 block_content = "allOf { branch 'main'; environment name: 'FOO', value: 'bar' }"
    则返回 [("allOf", "branch 'main'; environment name: 'FOO', value: 'bar'")]
    """
    results = []
    idx = 0
    length = len(block_content)

    while idx < length:
        # 跳过空白
        while idx < length and block_content[idx].isspace():
            idx += 1
        if idx >= length:
            break

        # 尝试匹配 cond_type
        # 可能是 allOf, anyOf, not, branch, environment...
        cond_match = re.match(
            r'(allOf|anyOf|not|branch|environment|tag|buildingTag|changelog|changeset|changeRequest|triggeredBy|expression|equals)\b',
            block_content[idx:])
        if not cond_match:
            # 无法识别 => 可能是花括号或分号之类，跳一下
            idx += 1
            continue

        cond_type = cond_match.group(1)
        start_of_type = idx
        idx += len(cond_type)

        # 如果 cond_type 后面跟着 '{' 表示这是一个嵌套块(如 allOf { ... })
        # 否则可能是普通的 condition line (比如 branch 'main')
        # => 判断下一个非空字符是否是 '{'
        #    如果是，则用大括号计数法提取
        #    如果不是，就用行尾/分号等来截取
        idx_temp = skip_spaces(block_content, idx)
        if idx_temp < length and block_content[idx_temp] == '{':
            # 解析大括号内容
            idx = idx_temp + 1  # 跳过 '{'
            brace_level = 1
            body_start = idx
            while idx < length and brace_level > 0:
                if block_content[idx] == '{':
                    brace_level += 1
                elif block_content[idx] == '}':
                    brace_level -= 1
                idx += 1
            body_end = idx - 1  # '}' 位置
            cond_body = block_content[body_start:body_end].strip()
            results.append((cond_type, cond_body))
        else:
            # 普通内置条件，直到行结束或分号
            cond_line = extract_line_until_delimiter(block_content, idx_temp)
            idx = idx_temp + len(cond_line)
            results.append((cond_type, cond_line.strip()))

    return results


def skip_spaces(text: str, idx: int) -> int:
    while idx < len(text) and text[idx].isspace():
        idx += 1
    return idx


def extract_line_until_delimiter(text: str, start_idx: int) -> str:
    """
    从 start_idx 往后抓取字符串，直到遇到换行、分号、或 '{', '}'（视为结束）为止。
    用于提取例如 "branch 'main'" 这种一行 condition 内容。
    """
    length = len(text)
    i = start_idx
    while i < length:
        if text[i] in ['\n', ';', '{', '}']:
            break
        i += 1
    return text[start_idx:i]


def split_condition_line(line: str) -> Tuple[str, str]:
    """
    对于类似 "branch 'main'"、"environment name:'DEPLOY_TO', value:'production'"
    这样的单行，拆分成 (cond_type, cond_body)。
    """
    # 先拿到cond_type => 第一个空格前的部分
    m = re.match(r'(\S+)\s+(.*)', line)
    if not m:
        return line.strip(), ""  # 无法进一步拆分
    return m.group(1), m.group(2)


def get_quoted_string(text: str) -> str:
    """
    从 text 中匹配 `'xxx'` 或 `"xxx"` 并返回 xxx。
    如果找不到，返回空字符串。
    仅取第一个出现的。
    """
    m = re.search(r'["\']([^"\']+)["\']', text)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------
# 5) 最终在转换阶段，把 parse_when_block 返回的字符串
#    放入 GitHub Actions job/step 的 if: ${{ ... }} 中
# ---------------------------------------------------------------------
def convert_jenkins_when_to_gha(stage_content: str) -> Dict[str, Any]:
    """
    演示：将一个 Jenkins stage 内容转换为 GH Actions job.steps 里的一个 step。
    如果 stage 存在 when 条件，则加上 if: ${{ ... }}。

    注意：这里只是示例。实际你可能会将 stage 拆成多个 steps、或有更多构建操作。
    """
    step_dict = {}

    when_expr = parse_when_block(stage_content)
    if when_expr:
        # GitHub Actions if 语法 => if: ${{ <expr> }}
        step_dict["if"] = f'${{{{ {when_expr} }}}}'
        logger.info(f"When_dict: {step_dict}")
    else:
        logger.info("没有when条件！")
    return step_dict


# 测试演示
if __name__ == "__main__":
    # 一个示例 stage，包含 when 块
    jenkins_stage_example = r"""

    when {
        branch 'main'
    }
    steps {
        echo "Test1"
    }

    """

    result_step = convert_jenkins_when_to_gha(jenkins_stage_example)
    print("=== Converted GH Actions Step ===")
    print(result_step)
    """
    预期输出类似：
    {
      'name': 'Stage: Build',
      'run': "echo 'Run stage steps here...'",
      'if': '${{ (github.ref == "refs/heads/main") && (env.DEPLOY_TO == "production") }}'
    }
    """


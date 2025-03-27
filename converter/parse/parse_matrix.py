import re
from converter.utils.getLogger import setup_logging
from typing import Dict, Any, List

logger = setup_logging()


def is_incomplete_jenkins_code(content: str) -> bool:
    """检查Jenkins代码是否不完整（括号不匹配）"""
    open_braces = content.count('{')
    close_braces = content.count('}')
    return open_braces != close_braces


def extract_block_content(content: str, block_name: str) -> str:
    """
    提取形如  block_name { ... } 的内容。
    通过大括号计数，找出与 block_name { 对应的那一对 }。
    """
    pattern = rf'{block_name}\s*\{{'
    start_match = re.search(pattern, content)
    if not start_match:
        return ""

    start_pos = start_match.end()
    # 如果整体不完整，直接返回余下内容
    if is_incomplete_jenkins_code(content):
        return content[start_pos:].strip()

    brace_count = 1
    end_pos = start_pos

    for i in range(start_pos, len(content)):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1

        if brace_count == 0:
            end_pos = i
            break

    return content[start_pos:end_pos].strip()


def extract_direct_axes(content: str) -> List[Dict[str, Any]]:
    """
    从给定字符串中提取所有的 `axis { ... }` 块，
    解析出 name / values / notValues，返回列表，每个元素形如:
    {
      "name": "PLATFORM",
      "values": ["linux","windows"]
    }
    或
    {
      "name": "PLATFORM",
      "not_values": ["windows"]
    }
    """
    axes = []

    # 查找所有axis定义
    axis_blocks = re.findall(r'axis\s*{([^}]+)}', content, re.DOTALL)
    if not axis_blocks:
        # 如果没有找到完整的 axis {}，再尝试不完整匹配
        axis_starts = re.findall(r'axis\s*{', content)
        if axis_starts:
            # 仅匹配一次的情况
            name_match = re.search(r"name\s+['\"](.*?)['\"]", content)
            values_match = re.search(r"values\s+(.*?)(?:$|$)", content, re.DOTALL)
            not_values_match = re.search(r"notValues\s+(.*?)(?:$|$)", content, re.DOTALL)

            if name_match:
                axis_dict = {"name": name_match.group(1)}

                if values_match:
                    values_str = values_match.group(1).strip()
                    values = _parse_value_list(values_str)
                    axis_dict["values"] = values

                if not_values_match:
                    not_values_str = not_values_match.group(1).strip()
                    not_values = _parse_value_list(not_values_str)
                    axis_dict["not_values"] = not_values

                axes.append(axis_dict)
        return axes

    for axis_block in axis_blocks:
        name_match = re.search(r"name\s+['\"](.*?)['\"]", axis_block)
        values_match = re.search(r"values\s+(.*?)(?:$|\n)", axis_block, re.DOTALL)
        not_values_match = re.search(r"notValues\s+(.*?)(?:$|\n)", axis_block, re.DOTALL)

        if name_match:
            axis_dict = {"name": name_match.group(1)}

            if values_match:
                values_str = values_match.group(1).strip()
                values = _parse_value_list(values_str)
                axis_dict["values"] = values

            if not_values_match:
                not_values_str = not_values_match.group(1).strip()
                not_values = _parse_value_list(not_values_str)
                axis_dict["not_values"] = not_values

            axes.append(axis_dict)

    return axes


def _parse_value_list(values_str: str) -> List[str]:
    """辅助函数: 解析形如 'linux', 'windows' 的值列表"""
    values = []
    value_matches = re.findall(r"['\"](.*?)['\"]", values_str)
    if value_matches:
        values.extend(value_matches)
    else:
        # 处理逗号分隔的值
        parts = values_str.split(',')
        values.extend([p.strip() for p in parts if p.strip()])
    return values


def extract_exclude_blocks(content: str) -> List[str]:
    """
    从给定 content 中，使用 bracket 计数法提取所有完整的 exclude { ... } 块。
    """
    blocks = []
    pattern = r'(exclude\s*\{)'
    for match in re.finditer(pattern, content):
        start_pos = match.end()
        brace_count = 1
        end_pos = start_pos
        for i in range(start_pos, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
            if brace_count == 0:
                end_pos = i
                break
        block_content = content[start_pos:end_pos].strip()
        blocks.append(block_content)
    return blocks


def parse_matrix_content(full_content: str) -> Dict[str, Any]:
    """
    解析Jenkins语法:
    matrix {
      axes { ... }
      excludes { ... }
    }
    返回: {
      "axes": [ { "name": "PLATFORM","values":["linux","windows","mac"] } ...],
      "excludes": [ { "PLATFORM": "linux", "BROWSER": "safari"}, ...]
    }
    """
    matrix_dict = {"axes": [], "excludes": []}

    # --- 如果有最外层的 matrix { ... }，先把它提取出来 ---
    matrix_block = extract_block_content(full_content, 'matrix')
    if matrix_block:
        content = matrix_block
    else:
        # 如果用户只给了 axes {...} excludes {...}，没有包裹 matrix { ... }，就直接用全部文本
        content = full_content

    # 1) 提取 "axes { ... }"
    axes_content = extract_block_content(content, 'axes')
    if axes_content:
        matrix_dict["axes"] = extract_direct_axes(axes_content)
    else:
        # 没找到单独块，就尝试直接搜 axis { ... }
        matrix_dict["axes"] = extract_direct_axes(content)

    # 2) 提取 "excludes { ... }" 整块，再解析其中多个 exclude { ... } 块
    excludes_content = extract_block_content(content, 'excludes')
    if excludes_content:
        exclude_blocks = extract_exclude_blocks(excludes_content)
        for exclude_block in exclude_blocks:
            axis_defs = extract_direct_axes(exclude_block)

            # 处理简单情况：所有轴都是直接的 values
            if all("values" in axis for axis in axis_defs):
                exclude_item = {}
                for axis in axis_defs:
                    name = axis.get("name")
                    vals = axis.get("values", [])
                    if name and vals:
                        # 假设只需要排除一项时，取 vals[0] 即可
                        exclude_item[name] = vals[0]
                if exclude_item:
                    matrix_dict["excludes"].append(exclude_item)

            # 处理包含 notValues 的情况
            else:
                # 找出所有可能的值组合
                axis_values = {}
                for axis in matrix_dict["axes"]:
                    axis_name = axis.get("name")
                    if axis_name:
                        axis_values[axis_name] = axis.get("values", [])

                # 对每个带有 notValues 的轴，生成所有需要排除的值
                exclusion_map = {}
                for axis in axis_defs:
                    name = axis.get("name")
                    if not name:
                        continue

                    if "values" in axis:
                        # 直接指定的值
                        exclusion_map[name] = axis["values"]
                    elif "not_values" in axis:
                        # 计算所有需要排除的值 (所有值 - not_values)
                        not_vals = axis["not_values"]
                        all_vals = axis_values.get(name, [])
                        # 保留不在 not_values 中的值
                        exclusion_map[name] = [v for v in all_vals if v not in not_vals]

                # 如果有 notValues，通常会生成多个排除项
                if exclusion_map:
                    # 找出所有存在于排除 map 中的轴
                    axes_names = list(exclusion_map.keys())
                    if len(axes_names) == 1:
                        # 单轴情况，每个值都是一个单独的排除项
                        name = axes_names[0]
                        for val in exclusion_map[name]:
                            matrix_dict["excludes"].append({name: val})
                    else:
                        # 多轴情况，需要生成笛卡尔积
                        # 例如：{PLATFORM: [linux, mac], BROWSER: [edge]} 会生成
                        # [{PLATFORM: linux, BROWSER: edge}, {PLATFORM: mac, BROWSER: edge}]

                        # 简单实现：假设只有两个轴，一个是 notValues，一个是常规 values
                        not_value_axis = None
                        regular_axis = None

                        for name in axes_names:
                            for axis in axis_defs:
                                if axis.get("name") == name:
                                    if "not_values" in axis:
                                        not_value_axis = name
                                    else:
                                        regular_axis = name

                        if not_value_axis and regular_axis:
                            for not_val in exclusion_map[not_value_axis]:
                                for reg_val in exclusion_map[regular_axis]:
                                    exclude_item = {
                                        not_value_axis: not_val,
                                        regular_axis: reg_val
                                    }
                                    matrix_dict["excludes"].append(exclude_item)

    return matrix_dict


def build_strategy_dict(matrix_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    将解析得到的 { "axes": [...], "excludes": [...] } 结构
    转换为 GitHub Actions 所需的 Dict[str, Any]，形如:

    {
      "strategy": {
        "matrix": {
          "PLATFORM": ["linux", "windows", "mac"],
          "BROWSER": ["chrome", "firefox", "safari"],
          "JDK": ["8","11"],
          "exclude": [
            {"PLATFORM": "linux","BROWSER": "safari"},
            ...
          ]
        }
      }
    }
    """
    # 构造最终的数据结构
    final_dict: Dict[str, Any] = {"strategy": {"matrix": {}}}

    # 先放入 axes
    for axis in matrix_dict.get("axes", []):
        name = axis.get("name")
        values = axis.get("values", [])
        if name and values:
            final_dict["strategy"]["matrix"][name] = values

    # 再放入 excludes
    excludes_list = matrix_dict.get("excludes", [])
    if excludes_list:
        final_dict["strategy"]["matrix"]["exclude"] = excludes_list

    return final_dict


def convert_jenkins_matrix(jenkins_content: str) -> Dict[str, Any]:
    """
    将Jenkins matrix语法(axes + excludes等)转换为
    **Python字典**形式的GitHub Actions配置结构。
    """
    if not jenkins_content or not jenkins_content.strip():
        logger.info("输入为空，无法解析Jenkins matrix")
        return {}

    try:
        matrix_config = parse_matrix_content(jenkins_content)
        logger.info(f"解析结果: {matrix_config}")

        if not matrix_config["axes"]:
            logger.info("未找到有效的matrix axes配置")
            return {}

        # 构造最终的 GHA Dict
        gha_dict = build_strategy_dict(matrix_config)
        logger.info(f"构造最终的 GHA Dict {gha_dict}")
        return gha_dict

    except Exception as e:
        logger.error(f"转换过程中发生错误: {str(e)}")
        return {}


if __name__ == "__main__":
    # 试一下较为复杂的代码片段:
    jenkins_matrix_code = r"""
    matrix {
                axes {
                    axis {
                        name 'PLATFORM'
                        values 'linux', 'windows', 'mac'
                    }
                    axis {
                        name 'BROWSER'
                        values 'chrome', 'firefox', 'safari'
                    }
                    axis {
                        name 'JDK'
                        values '8', '11'
                    }
                }
                excludes {

                    exclude {
                        axis {
                            name 'PLATFORM'
                            values 'linux'
                        }
                        axis {
                            name 'BROWSER'
                            values 'safari'
                        }
                        }

                    exclude {
                        axis {
                            name 'PLATFORM'
                            values 'mac'
                        }
                        axis {
                            name 'JDK'
                            values '8'
                        }
                    }

                    exclude {
                        axis {
                            name 'BROWSER'
                            values 'chrome'
                        }
                        axis {
                            name 'JDK'
                            values '11'
                        }
                    }
                }
                steps {
                    echo "Building the project"
                    sh 'mvn clean install'
                }
            }

    """
    jenkins_matrix_code2 = r"""
    stage('BuildAndTest') {
            matrix {
                axes {
                    axis {
                        name 'PLATFORM'
                        values 'linux', 'windows', 'mac'
                    }
                    axis {
                        name 'BROWSER'
                        values 'firefox', 'chrome', 'safari', 'edge'
                    }
                }
                excludes {
                    exclude {
                        axis {
                            name 'PLATFORM'
                            notValues 'windows'
                        }
                        axis {
                            name 'BROWSER'
                            values 'edge'
                        }
                    }
                }
                stages {
                    stage('Build6666666666') {
                        steps {
                            echo "Do Build for ${PLATFORM} - ${BROWSER}"
                        }
                    }
                    stage('Test666666666666') {
                        steps {
                            echo "Do Test for ${PLATFORM} - ${BROWSER}"
                        }
                    }
                }
            }
        }
    """

    result_dict = convert_jenkins_matrix(jenkins_matrix_code)
    logger.info(f"====== 转换结果(字典) ======\n {result_dict}")


import re
from typing import List, Dict, Any

from converter.utils.split_steps_content import split_steps_content
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def parse_jenkins_steps(steps_content: str) -> List[Dict[str, Any]]:
    """
    将原先对 steps_content 的解析逻辑抽取为独立函数。

    :param steps_content: 形如 Jenkinsfile.groovy 里 steps { ... } 内部的原始文本
    :return: 解析后的步骤列表，每个元素是一个字典，包含对 step 的各种字段提取结果
    """
    logger.info(f"steps_content: {steps_content}")
    logger.info(f"Length of steps_content: {len(steps_content)}")

    steps = []
    if not steps_content:
        # 如果 steps_content 为空或找不到，直接返回空列表
        return steps

    # 使用 split_steps_content 函数分割步骤
    split_steps = split_steps_content(steps_content)
    logger.info(f"Split Steps Length: {len(split_steps)}")
    logger.info(f"Split Steps: {split_steps}")

    for step_str in split_steps:
        logger.info(f"Step_str: {step_str}")
        step_str = step_str.strip()
        if not step_str:
            continue

        # --- 1) 匹配赋值步骤（带方法链） ---
        assignment_pattern = re.compile(
            r'^(?:def\s+)?(\w+)\s*=\s*'  # 变量名（可选 def 关键字）
            r'(\w+)\s*\(\s*(.*?)\s*\)'  # 函数名和参数部分（非贪婪匹配到第一个闭合括号）
            r'((?:\.\w+\s*\([^)]*\))*)\s*$',  # 方法链部分（如 .trim()）
            re.DOTALL
        )
        match = assignment_pattern.match(step_str)
        if match:
            var_name = match.group(1)
            func_name = match.group(2)
            raw_args = match.group(3).strip()
            method_chain = match.group(4).strip()

            # 解析参数部分
            args_dict = {}
            if raw_args:
                args_pattern = re.compile(
                    r'(\w+)\s*:\s*'
                    r'('
                    r'''(?:'[^']*'|"[^"]*")'''  # 单/双引号包裹
                    r'|[\w\.\$]+'
                    r')',
                    re.DOTALL
                )
                for arg_match in args_pattern.finditer(raw_args):
                    key = arg_match.group(1)
                    value = arg_match.group(2).strip('\'"')
                    args_dict[key] = value

            # 解析方法链（如 .trim()）
            methods = []
            if method_chain:
                method_pattern = re.compile(
                    r'\.(\w+)\s*\(\s*([^)]*)\s*\)',
                    re.DOTALL
                )
                for method_match in method_pattern.finditer(method_chain):
                    method_name = method_match.group(1)
                    method_args = method_match.group(2).strip('\'"')
                    methods.append({
                        'method': method_name,
                        'args': method_args
                    })

            logger.debug(
                f"Parsed assignment step: var_name='{var_name}', func_name='{func_name}', args='{args_dict}', methods='{methods}'")
            steps.append({
                'name': 'assignment',
                'var_name': var_name,
                'func_name': func_name,
                'args': args_dict,
                'methods': methods
            })
            continue

        # --- 2) 匹配带括号和代码块的函数调用，例如 withCredentials(...) { ... } ---
        match = re.match(r'^(\w+)\s*\((.*)\)\s*\{\s*(.*?)\s*\}$', step_str, re.DOTALL)
        if match:
            step_name = match.group(1)
            raw_args = match.group(2)
            raw_block = match.group(3)
            logger.debug(
                f"Parsed step with parentheses and block: name='{step_name}', args='{raw_args}', block='{raw_block}'")
            steps.append({
                'name': step_name,
                'raw_args': raw_args,
                'raw_block': raw_block
            })
            continue

        # --- 3) 匹配带括号的函数调用，例如 git(url: '...', branch: '...') ---
        match = re.match(r'^(\w+)\s*\((.*)\)$', step_str, re.DOTALL)
        if match:
            step_name = match.group(1)
            raw_args = match.group(2)
            logger.debug(f"Parsed step with parentheses: name='{step_name}', args='{raw_args}'")
            steps.append({
                'name': step_name,
                'raw_args': raw_args
            })
            continue

        # --- 4) 匹配带引号的命令，例如 sh 'make build' 或 echo "message" ---
        match = re.match(r'^(\w+)\s+["\'](.*)["\']$', step_str, re.DOTALL)
        if match:
            step_name = match.group(1)
            raw_args = match.group(2)
            logger.debug(f"Parsed step with quotes: name='{step_name}', args='{raw_args}'")
            steps.append({
                'name': step_name,
                'raw_args': raw_args
            })
            continue

        # --- 5) 匹配代码块，例如 script { ... } ---
        match = re.match(r'^(\w+)\s*\{(.*)\}$', step_str, re.DOTALL)
        if match:
            step_name = match.group(1)
            raw_args = match.group(2).strip()
            logger.debug(f"Parsed step with block: name='{step_name}', args='{raw_args}'")
            steps.append({
                'name': step_name,
                'raw_args': raw_args
            })
            continue

        # --- 6) 匹配多参数步骤，例如 git branch: 'main', url: '...', credentialsId: '...' ---
        multi_param_pattern = re.compile(
            r'^(\w+)\s+'  # 步骤名称
            r'('
            r'(?:[\w]+:\s*(?:\'[^\']*?\'|"[^"]*?"|\w+)\s*,?\s*)+'  # 键值对列表
            r')',
            re.DOTALL
        )
        if match := multi_param_pattern.match(step_str):
            step_name = match.group(1)
            raw_args = match.group(2)
            logger.debug(f"Parsed multi-parameter step: name='{step_name}', args='{raw_args}'")

            arg_pattern = re.compile(
                r'(\w+)\s*:\s*'
                r'('
                r'''\'([^\']*?)\''''  # 单引号值 -> 第3组
                r'|"([^"]*?)"'  # 双引号值 -> 第4组
                r'|([^,\s]+)'  # 无引号值 -> 第5组
                r')',
                re.DOTALL
            )
            args_dict = {}
            for arg_match in arg_pattern.finditer(raw_args):
                key = arg_match.group(1)
                # 提取三种可能的值（优先引号值）
                value = arg_match.group(3) or arg_match.group(4) or arg_match.group(5)
                args_dict[key] = value

            logger.debug(f"Parsed multi-parameter step: name='{step_name}', args_dict='{args_dict}'")
            steps.append({
                'name': step_name,
                'raw_args': args_dict
            })
            continue

        # --- 7) 匹配带命名空间的步骤调用，例如 govuk.buildProject(...) ---
        method_chain_pattern = re.compile(
            r'^([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\s*\((.*?)\)\s*(\.\w+\([^\)]*\))?$',
            re.DOTALL
        )
        match = method_chain_pattern.match(step_str)
        if match:
            step_name = match.group(1)
            raw_args = match.group(2)
            method_chain = match.group(3) if match.group(3) else None

            args_dict = {}
            args_pattern = re.compile(r'(\w+)\s*:\s*([^,]+)')
            for arg_match in args_pattern.finditer(raw_args):
                key = arg_match.group(1)
                value = arg_match.group(2).strip('\'"')
                args_dict[key] = value

            logger.debug(
                f"Parsed dot-space step: name='{step_name}', args_dict='{args_dict}', method_chain='{method_chain}'")
            steps.append({
                'name': step_name,
                'args_dict': args_dict,
                'method_chain': method_chain
            })
            continue

        # --- 8) 未识别到的格式，作为原始内容处理 ---
        logger.warning(f"Unrecognized step format: {step_str}")
        steps.append({
            'content': step_str
        })

    return steps

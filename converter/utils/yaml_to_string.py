from typing import Dict, Any
from ruamel.yaml import YAML
from io import StringIO
from ruamel.yaml.comments import CommentedSeq, CommentedMap
import copy


def yaml_to_string(yaml_dict: Dict[str, Any]) -> str:
    """
    将YAML字典转换为格式化字符串，对特定字段使用流式风格并保持字段顺序：
    1. jobs.<job_name>.needs 或 <job_name>.needs
    2. jobs.<job_name>.strategy.matrix.PLATFORM, BROWSER等矩阵条目

    Args:
        yaml_dict: YAML字典

    Returns:
        格式化的YAML字符串
    """
    # 深拷贝字典，避免修改原始数据
    modified_dict = copy.deepcopy(yaml_dict)

    # 处理workflow_dispatch.inputs下的options字段
    if 'on' in modified_dict and 'workflow_dispatch' in modified_dict['on'] and 'inputs' in modified_dict['on'][
        'workflow_dispatch']:
        inputs = modified_dict['on']['workflow_dispatch']['inputs']
        for input_name, input_config in inputs.items():
            if 'options' in input_config and isinstance(input_config['options'], list):
                seq = CommentedSeq(input_config['options'])
                seq.fa.set_flow_style()
                input_config['options'] = seq

    # 判断是否存在jobs字段
    if 'jobs' in modified_dict:
        # 遍历jobs下的所有任务
        ordered_jobs = CommentedMap()
        for job_name, job_config in modified_dict['jobs'].items():
            # 处理和重排顺序
            ordered_job_config = process_job_config(job_config)
            ordered_jobs[job_name] = ordered_job_config
        modified_dict['jobs'] = ordered_jobs
    else:
        # 检查是否是直接的job配置（没有jobs父键）
        # 判断特征：查找job配置可能含有的字段如needs, runs-on, steps等
        is_job_config = False
        for key in modified_dict:
            if isinstance(modified_dict[key], dict) and (
                    'needs' in modified_dict[key] or 'runs-on' in modified_dict[key] or 'steps' in modified_dict[key]):
                is_job_config = True
                modified_dict[key] = process_job_config(modified_dict[key])

        # 如果顶层本身就像是一个job配置
        if not is_job_config and any(k in modified_dict for k in ['needs', 'runs-on', 'steps']):
            modified_dict = process_job_config(modified_dict)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    string_stream = StringIO()
    yaml.dump(modified_dict, string_stream)
    return string_stream.getvalue()


def process_job_config(job_config):
    """
    处理单个job配置并按照指定顺序排序字段

    Args:
        job_config: job配置字典

    Returns:
        重新排序后的job配置
    """
    # 创建一个新的有序字典来保持字段顺序
    ordered_config = CommentedMap()

    # 定义字段优先级顺序(不包含steps)
    field_order = ['name', 'runs-on', 'needs', 'if']

    # 处理needs字段，设置为流式风格
    if 'needs' in job_config and isinstance(job_config['needs'], list):
        # 创建一个特殊标记，使其使用流式风格
        seq = CommentedSeq(job_config['needs'])
        seq.fa.set_flow_style()
        job_config['needs'] = seq

    # 处理strategy.matrix下的数组字段
    if 'strategy' in job_config and 'matrix' in job_config['strategy']:
        matrix = job_config['strategy']['matrix']
        # 遍历matrix下的所有键值对
        for key, value in list(matrix.items()):
            # 只处理简单数组，排除exclude/include等复杂对象
            if isinstance(value, list) and key not in ['exclude', 'include'] and all(
                    not isinstance(item, dict) for item in value):
                seq = CommentedSeq(value)
                seq.fa.set_flow_style()
                matrix[key] = seq

    # 按照指定顺序添加字段
    # 首先添加优先字段(不包括steps)
    for field in field_order:
        if field in job_config:
            ordered_config[field] = job_config[field]

    # 然后添加其他字段(除了steps)
    for field, value in job_config.items():
        if field not in field_order and field != 'steps':
            ordered_config[field] = value

    # 最后添加steps字段(如果存在)
    if 'steps' in job_config:
        ordered_config['steps'] = job_config['steps']

    return ordered_config

import os
import json
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from converter.interface import convert_jenkins_to_actions

app = Flask(__name__)

# 配置
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')


@app.route('/api/convert-file', methods=['POST'])
def convert_file():
    """处理文件上传并转换"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件部分'}), 400

    files = request.files.getlist('file')
    results = []

    for file in files:
        if file.filename == '':
            continue

        if file:
            try:
                # 保存上传的文件
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # 读取文件内容
                with open(filepath, 'r', encoding='utf-8') as f:
                    jenkins_content = f.read()

                # 调用转换接口
                convert_result = convert_jenkins_to_actions(jenkins_content)

                # 生成GitHub Actions文件名
                if filename.lower() == 'jenkinsfile':
                    actions_filename = '.github/workflows/main.yml'
                else:
                    base_filename = os.path.splitext(filename)[0]
                    actions_filename = f'.github/workflows/{base_filename}.yml'

                # 添加到结果列表
                results.append({
                    'jenkinsFileName': filename,
                    'actionsFileName': actions_filename,
                    'jenkinsFileContent': jenkins_content,
                    # actionsFileContent 用后端解析好的 YAML
                    'actionsFileContent': convert_result['actions_file_content'],
                    # 关键：将详细对比也放到返回里
                    'detailedComparison': convert_result['detailed_comparison']
                })

                # 删除临时文件
                os.remove(filepath)

            except Exception as e:
                return jsonify({'error': str(e)}), 500

    return jsonify({'results': results})


@app.route('/api/convert-content', methods=['POST'])
def convert_content():
    """处理手动输入的Jenkinsfile内容"""
    data = request.json

    if not data or 'content' not in data:
        return jsonify({'error': '未提供内容'}), 400

    jenkins_content = data['content']
    filename = data.get('filename', 'Jenkinsfile.groovy')

    try:
        # 调用转换接口
        convert_result = convert_jenkins_to_actions(jenkins_content)
        # 生成GitHub Actions文件名
        if filename.lower() == 'jenkinsfile':
            actions_filename = '.github/workflows/main.yml'
        else:
            base_filename = os.path.splitext(filename)[0]
            actions_filename = f'.github/workflows/{base_filename}.yml'

        result = {
            'jenkinsFileName': filename,
            'actionsFileName': actions_filename,
            'jenkinsFileContent': jenkins_content,
             # actionsFileContent 用后端解析好的 YAML
            'actionsFileContent': convert_result['actions_file_content'],
            # 关键：将详细对比也放到返回里
            'detailedComparison': convert_result['detailed_comparison']
        }

        return jsonify({'result': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

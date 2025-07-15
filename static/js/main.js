const { createApp, ref, reactive, computed, watch, onMounted } = Vue;

createApp({
    delimiters: ['${', '}'], // 修改Vue的定界符
    setup() {
        const fileInput = ref(null);
        const folderInput = ref(null);
        const jenkinsContentInput = ref(null);
        const isDragging = ref(false);
        const isProcessing = ref(false);
        const results = ref([]);
        const showComparisonDialog = ref(false);
        const activeTab = ref('side-by-side');
        const currentComparison = ref(null);

        // 手动输入相关状态
        const showInputDialog = ref(false);
        const jenkinsInputContent = ref('');
        const jenkinsInputFileName = ref('Jenkinsfile.groovy');

        // 获取当前时间
        function getCurrentTime() {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0'); // 月份从0开始，需+1
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
        }

        // 详细对比数据
        const detailedComparison = computed(() => {
            if (!currentComparison.value) return [];

            // 如果后端已经返回了 detailedComparison 数组，就直接用
            if (currentComparison.value.detailedComparison
                && currentComparison.value.detailedComparison.length > 0) {
                return currentComparison.value.detailedComparison;
            }

            // 简单的分块对比逻辑
            return generateDetailedComparison(
                currentComparison.value.jenkinsFileContent,
                currentComparison.value.actionsFileContent
            );
        });

        // 生成详细对比数据
        function generateDetailedComparison(jenkinsContent, actionsContent) {
            // 改进的解析逻辑，更智能地匹配Jenkins和GitHub Actions语句
            const jenkinsLines = jenkinsContent.split('\n');
            const actionsLines = actionsContent.split('\n');
            const result = [];

            // 定义常见对应关系
            const commonMappings = [
                {
                    jenkinsPattern: /checkout\s+scm/i,
                    actionsContent: '- uses: actions/checkout@v2'
                },
                {
                    jenkinsPattern: /stage\s*\(\s*['"]?Build['"]?/i,
                    actionsContent: '- name: Build\n  run: echo "Building application"'
                },
                {
                    jenkinsPattern: /stage\s*\(\s*['"]?Test['"]?/i,
                    actionsContent: '- name: Test\n  run: echo "Running tests"'
                },
                {
                    jenkinsPattern: /stage\s*\(\s*['"]?Deploy['"]?/i,
                    actionsContent: '- name: Deploy\n  run: echo "Deploying application"'
                },
                {
                    jenkinsPattern: /docker\.build/i,
                    actionsContent: '- name: Build Docker image\n  run: docker build -t myapp .'
                }
            ];

            // 尝试根据模式匹配
            let jenkinsChunks = [];
            let currentChunk = [];

            // 把Jenkins内容分块，每个stage为一块
            jenkinsLines.forEach((line, index) => {
                currentChunk.push(line);

                // 如果是stage定义行或包含关键字的行
                if (line.trim().match(/stage\s*\(/i) && index > 0) {
                    jenkinsChunks.push(currentChunk.join('\n'));
                    currentChunk = [line];
                }
            });

            // 添加最后一个块
            if (currentChunk.length > 0) {
                jenkinsChunks.push(currentChunk.join('\n'));
            }

            // 如果没有成功分块，使用整个内容作为一个块
            if (jenkinsChunks.length === 0) {
                jenkinsChunks = [jenkinsContent];
            }

            // 对每个Jenkins块找到最匹配的Actions块
            jenkinsChunks.forEach(jenkinsChunk => {
                let matchFound = false;

                // 尝试使用预定义的映射
                for (const mapping of commonMappings) {
                    if (jenkinsChunk.match(mapping.jenkinsPattern)) {
                        result.push({
                            jenkins: jenkinsChunk,
                            actions: mapping.actionsContent
                        });
                        matchFound = true;
                        break;
                    }
                }

                // 如果没有匹配，则使用简单的启发式方法
                if (!matchFound) {
                    // 提取阶段名或关键词
                    const stageMatch = jenkinsChunk.match(/stage\s*\(\s*['"]([^'"]+)['"]/);
                    const stageName = stageMatch ? stageMatch[1].toLowerCase() : '';

                    // 在Actions内容中查找类似的部分
                    let matchingActions = '';

                    if (stageName) {
                        // 在GitHub Actions中查找包含类似阶段名的步骤
                        const actionSteps = actionsContent.split(/\s+-\s+/).filter(step => {
                            if (stageName === 'build' && step.includes('Build')) return true;
                            if (stageName === 'test' && step.includes('Test')) return true;
                            if (stageName === 'deploy' && step.includes('Deploy')) return true;
                            if (stageName === 'checkout' && step.includes('checkout')) return true;
                            return step.toLowerCase().includes(stageName.toLowerCase());
                        });

                        if (actionSteps.length > 0) {
                            matchingActions = '- ' + actionSteps.join('\n- ');
                        } else {
                            // 如果找不到匹配，使用默认内容
                            if (jenkinsChunk.includes('checkout')) {
                                matchingActions = '- uses: actions/checkout@v2';
                            } else if (jenkinsChunk.toLowerCase().includes('build')) {
                                matchingActions = '- name: Build\n  run: echo "Building"';
                            } else if (jenkinsChunk.toLowerCase().includes('test')) {
                                matchingActions = '- name: Test\n  run: echo "Testing"';
                            } else if (jenkinsChunk.toLowerCase().includes('deploy')) {
                                matchingActions = '- name: Deploy\n  run: echo "Deploying"';
                            } else {
                                matchingActions = '# Corresponding GitHub Actions code';
                            }
                        }
                    } else {
                        // 没有识别到阶段名
                        matchingActions = '# GitHub Actions equivalent code';
                    }

                    result.push({
                        jenkins: jenkinsChunk,
                        actions: matchingActions
                    });
                }
            });

            return result;
        }

        // 打开手动输入对话框
        function openInputDialog() {
            showInputDialog.value = true;
            // 延迟聚焦到文本框
            setTimeout(() => {
                if (jenkinsContentInput.value) {
                    jenkinsContentInput.value.focus();
                }
            }, 100);
        }

        // 加载Jenkins示例
        function loadJenkinsExample() {
            // 提供一个典型的示例Jenkinsfile
            jenkinsInputContent.value = `// 声明式Jenkinsfile示例
pipeline {
    agent any
    
    stages {
        stage('Checkout') {
            steps {
                sh 'checkout scm'
            }
        }
        
        stage('Build') {
            steps {
                sh 'echo "Building the application"'
                sh 'mvn clean package'
            }
        }
        
        stage('Test') {
            steps {
                sh 'echo "Running tests"'
                sh 'mvn test'
            }
            post {
                always {
                    sh 'echo "Running Always"'
                }
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh 'echo "Deploying the application"'
            }
        }
    }
    
    post {
        success {
            echo 'Build successful!'
        }
        failure {
            echo 'Build failed!'
        }
    }
}`;
        }

        // 触发文件上传
        function triggerFileUpload() {
            fileInput.value.click();
        }

        // 触发文件夹上传
        function triggerFolderUpload() {
            folderInput.value.click();
        }

        // 处理文件上传
        function handleFileUpload(event) {
            const files = event.target.files;
            if (files.length > 0) {
                processFiles(Array.from(files));
            }
        }

        // 处理文件夹上传
        function handleFolderUpload(event) {
            const files = event.target.files;
            if (files.length > 0) {
                processFiles(Array.from(files));
            }
        }

        // 处理文件拖放
        function handleFileDrop(event) {
            isDragging.value = false;
            const items = event.dataTransfer.items;
            const files = [];

            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    files.push(file);
                }
            }

            if (files.length > 0) {
                processFiles(files);
            }
        }

        // 处理文件夹拖放
        function handleFolderDrop(event) {
            isDragging.value = false;
            const items = event.dataTransfer.items;
            const files = [];

            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    files.push(file);
                }
            }

            if (files.length > 0) {
                processFiles(files);
            }
        }

        // 处理文件 - 与Flask后端通信
        function processFiles(files) {
            isProcessing.value = true;

            // 筛选合适的Jenkins文件
            const jenkinsFiles = files.filter(file => {
                const fileName = file.name.toLowerCase();
                return fileName === 'jenkinsfile' ||
                    fileName.includes('jenkins') ||
                    fileName.endsWith('.jenkins') ||
                    fileName.endsWith('.groovy') ||
                    fileName.endsWith('.jdp') ||
                    fileName.includes('pipeline') ||
                    fileName.includes('build');
            });

            if (jenkinsFiles.length === 0) {
                alert("未能识别到有效的Jenkins配置文件，请确认上传的文件是否正确。");
                isProcessing.value = false;
                return;
            }

            // 创建FormData对象，添加文件
            const formData = new FormData();
            jenkinsFiles.forEach(file => {
                formData.append('file', file);
            });

            // 发送到Flask后端
            fetch('/api/convert-file', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('网络响应不正常');
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }

                // 添加时间戳并更新结果
                const newResults = data.results.map(item => ({
                    ...item,
                    convertTime: getCurrentTime()
                }));

                results.value = [...results.value, ...newResults];
                isProcessing.value = false;
            })
            .catch(error => {
                console.error('处理文件时出错:', error);
                alert(`处理文件时出错: ${error.message}`);
                isProcessing.value = false;
            });
        }

        // 处理手动输入的内容
        function processInputContent() {
            if (!jenkinsInputContent.value.trim()) {
                alert("请输入Jenkins配置文件内容");
                return;
            }

            isProcessing.value = true;
            showInputDialog.value = false;

            // 准备发送的数据
            const data = {
                content: jenkinsInputContent.value,
                filename: jenkinsInputFileName.value.trim() || 'Jenkinsfile.groovy'
            };

            // 发送到Flask后端
            fetch('/api/convert-content', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('网络响应不正常');
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }

                // 添加时间戳并更新结果
                const result = {
                    ...data.result,
                    convertTime: getCurrentTime()
                };

                results.value = [...results.value, result];

                // 重置输入
                jenkinsInputContent.value = '';
                jenkinsInputFileName.value = 'Jenkinsfile.groovy';

                isProcessing.value = false;
            })
            .catch(error => {
                console.error('处理输入内容时出错:', error);
                alert(`处理输入内容时出错: ${error.message}`);
                isProcessing.value = false;
            });
        }

        // 打开对比对话框
        function openComparisonDialog(item) {
            currentComparison.value = item;
            showComparisonDialog.value = true;
            activeTab.value = 'side-by-side';

            // 在下一个 tick 中触发代码高亮
            Vue.nextTick(() => {
                // 强制重新初始化Prism
                if (window.Prism) {
                    setTimeout(() => {
                        try {
                            window.Prism.highlightAll();
                        } catch (e) {
                            console.error("Prism高亮错误:", e);
                        }
                    }, 50);
                }
            });
        }

        // 下载单个文件
        function downloadFile(item) {
            const blob = new Blob([item.actionsFileContent], { type: 'text/yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = item.actionsFileName.split('/').pop();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        // 批量下载所有文件
        function downloadAllFiles() {
            results.value.forEach(item => {
                downloadFile(item);
            });
        }

        // 当对话框显示时，禁止背景滚动
        watch(showComparisonDialog, (newVal) => {
            if (newVal) {
                document.body.style.overflow = 'hidden';
            } else {
                document.body.style.overflow = '';
            }
        });

        // 同样处理手动输入对话框的滚动
        watch(showInputDialog, (newVal) => {
            if (newVal) {
                document.body.style.overflow = 'hidden';
            } else {
                document.body.style.overflow = '';
            }
        });

        onMounted(() => {
            // 设置Prism插件选项
            if (window.Prism && window.Prism.plugins && window.Prism.plugins.NormalizeWhitespace) {
                window.Prism.plugins.NormalizeWhitespace.setDefaults({
                    'remove-trailing': true,
                    'remove-indent': true,
                    'left-trim': true,
                    'right-trim': true
                });
            }

            // 监听选项卡切换，重新应用代码高亮
            watch(activeTab, () => {
                Vue.nextTick(() => {
                    if (window.Prism) {
                        setTimeout(() => {
                            window.Prism.highlightAll();
                        }, 50);
                    }
                });
            });

            // 监听对话框打开状态，触发高亮
            watch(showComparisonDialog, (isOpen) => {
                if (isOpen) {
                    Vue.nextTick(() => {
                        if (window.Prism) {
                            setTimeout(() => {
                                window.Prism.highlightAll();

                                // 设置详细对比中左右两侧的等高
                                const comparisonItems = document.querySelectorAll('.comparison-item');
                                comparisonItems.forEach(item => {
                                    const left = item.querySelector('.comparison-jenkins');
                                    const right = item.querySelector('.comparison-actions');
                                    if (left && right) {
                                        const maxHeight = Math.max(
                                            left.scrollHeight,
                                            right.scrollHeight
                                        );

                                        // 如果内容高度小于最大高度限制，则设置实际高度
                                        // 否则使用限制高度并保持滚动

                                        left.style.height = `${maxHeight}px`;
                                        right.style.height = `${maxHeight}px`;


                                        const leftPre = left.querySelector('pre');
                                        const rightPre = right.querySelector('pre');

                                        if (leftPre && rightPre) {
                                            leftPre.style.height = '100%';
                                            rightPre.style.height = '100%';
                                        }

                                    }
                                });
                            }, 50);
                        }
                    });
                }
            });
        });

        return {
            fileInput,
            folderInput,
            jenkinsContentInput,
            isDragging,
            isProcessing,
            results,
            showComparisonDialog,
            activeTab,
            currentComparison,
            detailedComparison,
            // 手动输入相关
            showInputDialog,
            jenkinsInputContent,
            jenkinsInputFileName,
            openInputDialog,
            loadJenkinsExample,
            processInputContent,
            // 原有功能
            triggerFileUpload,
            triggerFolderUpload,
            handleFileUpload,
            handleFolderUpload,
            handleFileDrop,
            handleFolderDrop,
            openComparisonDialog,
            downloadFile,
            downloadAllFiles
        };
    }
}).mount('#app');
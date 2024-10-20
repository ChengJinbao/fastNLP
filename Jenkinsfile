pipeline {
    agent none
    environment {
        PJ_NAME = 'fastNLP'
        POST_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/14719364-818d-4f88-9057-7c9f0eaaf6ae'
    }
    stages {
        stage('Parallel Stages') {
            parallel {
                stage('Test Other'){
                    agent {
                        docker {
                            image 'fnlp:other'
                            args '-u root:root -v ${JENKINS_HOME}/html/docs:/docs -v ${JENKINS_HOME}/html/_ci:/ci'
                        }
                    }
                    steps {
                        sh 'pytest ./tests --durations=0 -m "not (torch or paddle or paddledist or jittor or torchpaddle or torchjittor)"'
                    }
                }
                stage('Test Torch-1.11') {
                    agent {
                        docker {
                            image 'fnlp:torch-1.11'
                            args '-u root:root -v ${JENKINS_HOME}/html/docs:/docs -v ${JENKINS_HOME}/html/_ci:/ci --gpus all --shm-size 256M'
                        }
                    }
                    steps {
                        sh 'pytest ./tests --durations=0 -m torch'
                    }
                }
                stage('Test Torch-1.6') {
                    agent {
                        docker {
                            image 'fnlp:torch-1.6'
                            args '-u root:root -v ${JENKINS_HOME}/html/docs:/docs -v ${JENKINS_HOME}/html/_ci:/ci --gpus all'
                        }
                    }
                    steps {
                        sh 'pytest ./tests/ --durations=0 -m torch'
                    }
                }
                stage('Test Paddle') {
                    agent {
                        docker {
                            image 'fnlp:paddle'
                            args '-u root:root -v ${JENKINS_HOME}/html/docs:/docs -v ${JENKINS_HOME}/html/_ci:/ci --gpus all'
                        }
                    }
                    steps {
                        sh 'pytest ./tests --durations=0 -m paddle --co'
                        sh 'FASTNLP_BACKEND=paddle pytest ./tests --durations=0 -m paddle --co'
                        sh 'FASTNLP_BACKEND=paddle pytest ./tests/core/drivers/paddle_driver/test_dist_utils.py --durations=0 --co'
                        sh 'FASTNLP_BACKEND=paddle pytest ./tests/core/drivers/paddle_driver/test_fleet.py --durations=0 --co'
                        sh 'FASTNLP_BACKEND=paddle pytest ./tests/core/controllers/test_trainer_paddle.py --durations=0 --co'
                    }
                }
                stage('Test Jittor') {
                    agent {
                        docker {
                            image 'fnlp:jittor'
                            args '-u root:root -v ${JENKINS_HOME}/html/docs:/docs -v ${JENKINS_HOME}/html/_ci:/ci --gpus all'
                        }
                    }
                    steps {
                        // sh 'pip install fitlog'
                        // sh 'pytest ./tests --html=test_results.html --self-contained-html'
                        sh 'pytest ./tests --durations=0 -m jittor --co'
                    }
                }
            }
        }
    }
    post {
        failure {
            sh 'post 1'
        }
        success {
            sh 'post 0'
            sh 'post github'
        }
    }
}
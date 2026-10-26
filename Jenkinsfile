pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Backend - Install') {
            steps {
                dir('backend') {
                    sh '''
                        python3 -m venv .venv
                        . .venv/bin/activate
                        pip install --upgrade pip
                        pip install -r requirements.txt
                        pip install pytest
                    '''
                }
            }
        }

        stage('Backend - Tests') {
            steps {
                dir('backend') {
                    sh '''
                        . .venv/bin/activate
                        pytest -v
                    '''
                }

            }
        }

        stage('Frontend - Install') {
            steps {
                dir('frontend') {
                    sh 'npm ci'
                }
            }
        }

        stage('Frontend - Build') {
            steps {
                dir('frontend') {
                    sh 'npm run build'
                }
            }
        }
    }

    post {
        success { echo 'Pipeline réussi ✅' }
        failure { echo 'Pipeline échoué ❌' }
    }
}
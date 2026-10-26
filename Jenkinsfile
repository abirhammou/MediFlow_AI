```groovy
pipeline {
    agent any

    stages {
        stage('1. Checkout GitHub') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('2. Backend - Install') {
            steps {
                dir('backend') {
                    sh '''
                        set -e
                        python3.12 --version
                        python3.12 -m venv .venv
                        .venv/bin/python -m pip install --upgrade pip
                        .venv/bin/python -m pip install -r requirements.txt
                        .venv/bin/python -m pip install pytest pytest-cov
                    '''
                }
            }
        }

        stage('3. Backend - Tests') {
            steps {
                dir('backend') {
                    sh '''
                        .venv/bin/python -m pytest -v \
                            --junitxml=pytest-report.xml \
                            --cov=. \
                            --cov-report=xml:coverage.xml
                    '''
                }
            }
            post {
                always {
                    junit(
                        testResults: 'backend/pytest-report.xml',
                        allowEmptyResults: true
                    )
                }
            }
        }

        stage('4. Frontend - Install') {
            steps {
                dir('frontend') {
                    sh 'npm ci'
                }
            }
        }

        stage('5. Frontend - Build') {
            steps {
                dir('frontend') {
                    sh 'npm run build'
                }
            }
        }

        stage('6. SonarQube Analysis') {
            steps {
                withSonarQubeEnv('SonarQube') {
                    sh '''
                        sonar-scanner \
                            -Dsonar.projectKey=MediFlow_AI \
                            -Dsonar.projectName=MediFlow_AI \
                            -Dsonar.sources=backend,frontend/src \
                            -Dsonar.exclusions=**/.venv/**,**/node_modules/**,**/__pycache__/**,**/coverage.xml,**/pytest-report.xml \
                            -Dsonar.python.coverage.reportPaths=backend/coverage.xml
                    '''
                }
            }
        }
    }

    post {
        success {
            echo 'Pipeline réussi : tests et analyse SonarQube terminés.'
        }
        failure {
            echo 'Pipeline échoué : consulter Console Output.'
        }
        always {
            echo 'Fin du pipeline.'
        }
    }
}
```
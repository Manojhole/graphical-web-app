pipeline {
    agent any

    environment {
        IMAGE_NAME = "ghcr.io/YOUR_GITHUB_USERNAME/graphical-web-app"
        KUBECONFIG = credentials('kubeconfig')
        GHCR_TOKEN = credentials('ghcr-token')
        GHCR_USER  = "YOUR_GITHUB_USERNAME"
    }

    stages {
        stage('Checkout Code') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/YOUR_GITHUB_USERNAME/graphical-web-app.git'
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    sh "docker build -t ${IMAGE_NAME}:latest ."
                }
            }
        }

        stage('Login to GHCR') {
            steps {
                script {
                    sh """
                        echo ${GHCR_TOKEN} | docker login ghcr.io -u ${GHCR_USER} --password-stdin
                    """
                }
            }
        }

        stage('Push Image') {
            steps {
                script {
                    sh "docker push ${IMAGE_NAME}:latest"
                }
            }
        }

        stage('Deploy to K3s') {
            steps {
                script {
                    sh """
                        mkdir -p ~/.kube
                        echo "${KUBECONFIG}" > ~/.kube/config
                        kubectl apply -f k8s/deployment.yaml
                        kubectl apply -f k8s/service.yaml
                    """
                }
            }
        }
    }
}

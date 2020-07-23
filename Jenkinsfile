#!groovy

def podYAML = """
spec:
  containers:
  - name: koji
    image: quay.io/bookwar/koji-client:0.0.1
    tty: true
"""

def dataFile = 'data.txt'

pipeline {

    agent {
	kubernetes {
	    yaml podYAML
	    defaultContainer 'koji'
	}
    }

    options {
        buildDiscarder(
            logRotator(
                numToKeepStr: '30',
                artifactNumToKeepStr: '30'
            )
        )
    }

    triggers {
        cron('H * * * *')
    }

    parameters{
	string(
	    name: 'LIMIT',
	    defaultValue: '5',
	    trim: true,
	    description: 'Number of builds to trigger. No for no builds.'
	    )
    }

    stages {
        stage('Collect stats') {
            steps {
                sh "./eln-check.py -o $dataFile"
	    }
	}
	stage('Trigger builds') {
	    steps {
		script {
		    def data = readFile dataFile
		    def builds = data.readLines()

		    Collections.shuffle(builds)
		    
		    limit = Math.min(builds.size(), params.LIMIT.toInteger())
		    toRebuild = builds[0..<limit]
		    
		    toRebuild.each {
			echo "Rebuilding $it"
			build (
			    job: 'eln-build-pipeline',
			    wait: false,
			    parameters:
				[
				string(name: 'KOJI_BUILD_ID', value: "$it"),
			    ]
			)
		    }
		}
            }
        }
    }
    post {
	success {
	    archiveArtifacts artifacts: dataFile
	}
    }
}

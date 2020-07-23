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

    parameters{
	string(
	    name: 'LIMIT',
	    defaultValue: '0',
	    trim: true,
	    description: 'Number of builds to trigger. No for no builds.'
	    )
    }

    stages {
        stage('Collect stats') {
            steps {
                sh "eln-check.py -o $dataFile"
		touch dataFile
	    }
	}
	stage('Trigger builds') {
	    steps {
		script {
		    data = File.readLines("$dataFile")
		    limit = params.LIMIT
		    BUILDS = data[0..<limit]
		    
		    env.BUILDS.each {
			echo "$it"
//			build (
//			    job: 'eln-build-pipeline',
//			    wait: false,
//			    parameters:
//				[
//				string(name: 'KOJI_BUILD_ID', value: "$it"),
//			    ]
//			)
		    }
		}
            }
        }
    }
}

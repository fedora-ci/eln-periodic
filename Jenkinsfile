#!groovy

def podYAML = '''
spec:
  containers:
  - name: koji
    image: quay.io/bookwar/koji-client:0.0.2
    tty: true
'''

def buildableFile = 'buildable-eln-packages.txt'
def dataFile = 'to_rebuild.txt'
def untagFile = 'to_untag.txt'
def statusFile = 'status.txt'
def statusRenderedFile = 'status.html'
def successrateFile = 'successrate.txt'

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
	disableConcurrentBuilds()
    }

    triggers {
	cron('H/30 * * * *')
    }

    parameters {
	string(
	name: 'LIMIT',
	defaultValue: '10',
	trim: true,
	description: 'Number of builds to trigger. No for no builds.'
	)
    }

    stages {
	stage('Collect stats') {
	    steps {
		sh "./eln-check.py -o $dataFile -s $statusFile -u $untagFile -r $successrateFile"
	    }
	}
	stage('Trigger builds') {
	    steps {
		script {
		    limit = params.LIMIT.toInteger()
		    if (limit == 0) {
			return
		    }

		    def data = readFile dataFile
		    def builds = data.readLines()

		    cut = Math.min(builds.size(), limit)

		    Collections.shuffle(builds)

		    toRebuild = builds[0..<cut]

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
	    archiveArtifacts artifacts: "$dataFile,$statusFile,$statusRenderedFile,$untagFile,$successrateFile,$buildableFile"
	}
    }
}

#!groovy

def buildableFile = 'buildable-eln-packages.txt'
def dataFile = 'to_rebuild.txt'
def untagFile = 'to_untag.txt'
def statusFile = 'status.txt'
def statusRenderedFile = 'status.html'
def successrateFile = 'successrate.html'
def composestatusFile = 'compose-status.html'

pipeline {
    agent { label 'eln' }

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
	cron('H * * * *')
    }

    parameters {
	string(
	name: 'LIMIT',
	defaultValue: '5',
	trim: true,
	description: 'Number of builds to trigger. No for no builds.'
	)
    }

    stages {
        stage('New stats') {
            steps {
                cleanWs deleteDirs: false
                checkout changelog: false, poll: false, scm: [
            $class: 'GitSCM',
            doGenerateSubmoduleConfigurations: false,
            extensions: [
            [
                $class: 'RelativeTargetDirectory',
                relativeTargetDir: 'eln'
            ]
            ],
            userRemoteConfigs: [
            [
                url: 'https://github.com/fedora-eln/eln'
            ]
            ]
        ]

                sh 'cd eln/ && ./compare/compare.py rawhide eln && cd .. && eln/scripts/eln-compose-status.py'
            }
        }
        stage('Collect stats') {
            steps {
                git "https://github.com/fedora-ci/eln-periodic.git"
                sh "$WORKSPACE/eln-check.py -o $dataFile -s $statusFile -u $untagFile -r $successrateFile"
            }
        }
    }
    post {
        success {
            archiveArtifacts artifacts: "$dataFile,$statusFile,$statusRenderedFile,$untagFile,$successrateFile,$buildableFile,$composestatusFile,eln/output/*"
        }
    }
}

# AWS EC2 Resources Cleaner

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg) [![License](https://img.shields.io/badge/license-MIT-green)](../LICENSE)

The AWS Resource Cleanup Script is a production-grade Python automation utility designed to identify and remove unused AWS resources such as stopped EC2 instances, unattached EBS volumes, old AMIs and orphaned snapshots.

This helps reduce costs, maintain hygiene, and improve governance in your AWS environment.

It’s built with safety-first principles, performing a dry run by default and supporting exclusion rules to protect critical resources.

## Features
🕵️‍♂️ Automatic Discovery

Scans your AWS account for:

Stopped EC2 instances older than a retention period

Unattached EBS volumes

AMIs older than a threshold (and their linked snapshots)

Orphaned snapshots (not linked to any AMI)

🧱 Safe by Default

Dry-run mode enabled by default – nothing is deleted unless you explicitly use --execute.

🔒 Exclusion Support

Exclude critical resources by:

Tag key (e.g. --exclude-tag DoNotDelete)

Tag key/value pair (e.g. --exclude-tag Environment=prod)

Explicit resource IDs (e.g. --exclude-id i-0123abcd)

🧩 Flexible Configuration

Supports region, profile, retention period, concurrency control, and max worker threads.

🪣 Logging and Audit

Logs all operations (both dry-run and execution) to:

Console output

Rotating log file (aws_cleanup.log)

Generates a JSON report (aws_cleanup_results_<timestamp>.json) for audit or CI/CD pipeline usage.

⚙️ Scalable and Concurrent

Uses Python’s ThreadPoolExecutor for efficient, parallel cleanup operations.

🛡️ Robust Error Handling

Handles boto3 and botocore exceptions gracefully with retry-safe operations.

🧰 Prerequisites
1. Python Environment

You’ll need:

Python 3.8+

The following libraries:

pip install boto3 python-dateutil

2. AWS Permissions

The AWS user/role running this script requires the following minimum permissions:

{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": [
        "ec2:DescribeInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeVolumes",
        "ec2:DeleteVolume",
        "ec2:DescribeImages",
        "ec2:DeregisterImage",
        "ec2:DescribeSnapshots",
        "ec2:DeleteSnapshot",
        "ec2:DescribeTags"
      ],
      "Resource": "*"
    }
  ]
}

3. AWS Credentials

Configure AWS credentials via one of the following:

~/.aws/credentials

Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION)

AWS named profile (use --profile flag)

IAM role attached to the EC2 instance or Lambda function running the script

🚀 Usage
1. Dry Run (default mode)

Lists resources that would be deleted — no deletion is performed.

python aws_cleanup.py --region us-east-1 --days 30

2. Execute (perform deletions)

Adds the --execute flag to actually delete identified resources.

python aws_cleanup.py --region us-east-1 --days 30 --execute

3. Exclude Critical Resources

Exclude by tag key, tag key=value, or resource ID.

# Exclude all tagged with 'DoNotDelete'
python aws_cleanup.py --region eu-west-1 --days 30 --exclude-tag DoNotDelete

# Exclude all prod environment resources
python aws_cleanup.py --region eu-west-1 --days 30 --exclude-tag Environment=prod

# Exclude specific resource IDs
python aws_cleanup.py --region us-east-1 --days 30 --exclude-id i-0123456789abcdef0 --exclude-id vol-0abcd1234

4. Use AWS Named Profile

If you use a specific AWS CLI profile:

python aws_cleanup.py --region ap-southeast-1 --profile myawsprofile

5. Control Concurrency

Limit concurrent API calls to avoid throttling:

python aws_cleanup.py --region us-east-1 --days 60 --max-workers 5

6. Command-Line Reference
Flag	Description	Default
--region	AWS region to target	Required
--profile	AWS named profile	None
--days	Retention threshold (in days)	30
--execute	Actually perform deletions (omit for dry-run)	False
--exclude-tag	Exclude by tag or tag=value	Optional
--exclude-id	Exclude by resource ID	Optional
--max-workers	Max parallel cleanup threads	10
📊 Sample Output
Console Output (Dry Run)
2025-11-13 12:10:14 [INFO] Starting cleanup: region=us-east-1, retention_days=30, dry_run=True
2025-11-13 12:10:15 [INFO] Scanning for stopped EC2 instances...
2025-11-13 12:10:16 [INFO] Found 2 stopped instances older than 30 days.
2025-11-13 12:10:16 [INFO] [DRY-RUN] Would terminate: ['i-0abc123456789def0', 'i-0def456789abc1234']
2025-11-13 12:10:17 [INFO] Scanning for unattached EBS volumes...
2025-11-13 12:10:18 [INFO] Found 3 unattached volumes older than 30 days.
2025-11-13 12:10:18 [INFO] [DRY-RUN] Would delete volume vol-0abcd12345ef67890
2025-11-13 12:10:19 [INFO] Scanning for old AMIs owned by self...
2025-11-13 12:10:19 [INFO] Found 1 AMI older than 30 days.
2025-11-13 12:10:19 [INFO] [DRY-RUN] Would deregister AMI ami-0a123bc456def7890
2025-11-13 12:10:20 [INFO] Scanning for orphaned snapshots...
2025-11-13 12:10:20 [INFO] Found 4 orphaned snapshots older than 30 days.
2025-11-13 12:10:20 [INFO] [DRY-RUN] Would delete snapshot snap-0abcd123456ef7890
2025-11-13 12:10:21 [INFO] Cleanup run complete.
2025-11-13 12:10:21 [INFO] Detailed results written to aws_cleanup_results_1731509421.json

Example JSON Report (aws_cleanup_results_1731509421.json)
{
  "stopped_instances_found": ["i-0abc123456789def0", "i-0def456789abc1234"],
  "terminate_instances": [{"Terminated": ["i-0abc123456789def0", "i-0def456789abc1234"]}],
  "volumes_found": ["vol-0abcd12345ef67890"],
  "delete_volumes": [{"VolumeId": "vol-0abcd12345ef67890", "Action": "DryRun"}],
  "amis_found": ["ami-0a123bc456def7890"],
  "deregister_amis": [{
    "ImageId": "ami-0a123bc456def7890",
    "Deregistered": "DryRun",
    "SnapshotResults": []
  }],
  "orphaned_snapshots_found": ["snap-0abcd123456ef7890"],
  "delete_snapshots": [{"SnapshotId": "snap-0abcd123456ef7890", "Action": "DryRun"}]
}

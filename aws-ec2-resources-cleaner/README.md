# AWS EC2 Resources Cleaner

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg) [![License](https://img.shields.io/badge/license-MIT-green)](../LICENSE)

The AWS Resource Cleanup Script is a production-grade Python automation utility designed to identify and remove unused AWS resources such as stopped EC2 instances, unattached EBS volumes, old AMIs and orphaned snapshots.

This helps reduce costs, maintain hygiene, and improve governance in your AWS environment.

It’s built with safety-first principles that performs a dry run by default and supporting exclusion rules to protect critical resources.

---

## Features
- Scans your AWS account for:
    - Stopped EC2 instances older than a retention period
    - Unattached EBS volumes
    - AMIs older than a threshold (and their linked snapshots)
    - Orphaned snapshots (not linked to any AMI)
- Dry-run mode enabled by default. Nothing is deleted unless you explicitly use `--execute`.
- Exclude critical resources by:
    - Tag key (for example, --exclude-tag DoNotDelete)
    - Tag key/value pair (for example, --exclude-tag Environment=prod)
    - Explicit resource IDs (for example, --exclude-id i-0123abcd)
- Supports region, profile, retention period, concurrency control and max worker threads.
- Logs all operations (both dry-run and execution) to console output as well as generates a JSON report (aws_cleanup_results_`timestamp`.json).
- Handles boto3 and botocore exceptions gracefully with retry-safe operations.

---

## Prerequisites
- Python Environment
    - You’ll need Python 3.8+
    - The following libraries:
    `pip install boto3 python-dateutil`
- AWS Permissions
    - The AWS user/role running this script requires the following minimum permissions:
    ```
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
    ```
- AWS Credentials
    - Configure AWS credentials via one of the following:
    - `~/.aws/credentials`
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION)
    - AWS named profile (use --profile flag)
    - IAM role attached to the EC2 instance or Lambda function running the script

---

## Usage
- Lists resources that would be deleted and no deletion is performed (default mode).
`python aws_cleanup.py --region us-east-1 --days 30`
- Add the `--execute` flag to actually delete identified resources.
`python aws_cleanup.py --region us-east-1 --days 30 --execute`
- Exclude critical resources by tag key, tag key=value or resource ID.
    - Exclude all tagged with 'DoNotDelete': `python aws_cleanup.py --region eu-west-1 --days 30 --exclude-tag DoNotDelete`
    - Exclude all prod environment resources: `python aws_cleanup.py --region eu-west-1 --days 30 --exclude-tag Environment=prod`
    - Exclude specific resource IDs: `python aws_cleanup.py --region us-east-1 --days 30 --exclude-id i-0123456789abcdef0 --exclude-id vol-0abcd1234`
- Use AWS Named Profile: `python aws_cleanup.py --region ap-southeast-1 --profile myawsprofile`
- Limit concurrent API calls to avoid throttling:: `python aws_cleanup.py --region us-east-1 --days 60 --max-workers 5`
- Command-Line Reference
```
Flag	            Description	                                        Default
--region	        AWS region to target	                            Required
--profile	        AWS named profile	                                None
--days	            Retention threshold (in days)	                    30
--execute	        Actually perform deletions (omit for dry-run)	    False
--exclude-tag	    Exclude by tag or tag=value	                        Optional
--exclude-id	    Exclude by resource ID	                            Optional
--max-workers	    Max parallel cleanup threads	                    10
```

---

## Sample Output
```
2025-11-13 16:41:30,727 [INFO] Starting cleanup: region=eu-west-2, retention_days=10, dry_run=True
2025-11-13 16:41:30,728 [INFO] Scanning for stopped EC2 instances...
2025-11-13 16:41:30,847 [INFO] Found 0 stopped instances older than 10 days.
2025-11-13 16:41:30,848 [INFO] Scanning for unattached EBS volumes...
2025-11-13 16:41:30,981 [INFO] Found 0 unattached volumes older than 10 days.
2025-11-13 16:41:30,981 [INFO] Scanning for old AMIs owned by self...
2025-11-13 16:41:31,176 [INFO] Found 2 AMIs older than 10 days.
2025-11-13 16:41:31,176 [INFO] AMI ami-0a4982e85f786a114 has 1 associated snapshot(s).
2025-11-13 16:41:31,177 [INFO] AMI ami-0abb5e1126e036bc1 has 1 associated snapshot(s).
2025-11-13 16:41:31,177 [INFO] [DRY-RUN] Would deregister AMI ami-0a4982e85f786a114
2025-11-13 16:41:31,177 [INFO] [DRY-RUN] Would deregister AMI ami-0abb5e1126e036bc1
2025-11-13 16:41:31,177 [INFO] [DRY-RUN] Would delete snapshot snap-05de73277a198be2e (associated with AMI ami-0a4982e85f786a114)
2025-11-13 16:41:31,178 [INFO] [DRY-RUN] Would delete snapshot snap-0ca53f223852e99b0 (associated with AMI ami-0abb5e1126e036bc1)
2025-11-13 16:41:31,184 [INFO] Scanning for orphaned snapshots owned by self...
2025-11-13 16:41:31,424 [INFO] Found 2 orphaned snapshots older than 10 days.
2025-11-13 16:41:31,425 [INFO] [DRY-RUN] Would delete snapshot snap-08a6f1b764b06b786
2025-11-13 16:41:31,425 [INFO] [DRY-RUN] Would delete snapshot snap-0a91ea3840c459668
2025-11-13 16:41:31,439 [INFO] Cleanup run complete.
2025-11-13 16:41:31,440 [INFO] Summary (high level):
2025-11-13 16:41:31,440 [INFO] Stopped instances found: 0
2025-11-13 16:41:31,440 [INFO] Volumes found: 0
2025-11-13 16:41:31,440 [INFO] AMIs found: 2
2025-11-13 16:41:31,440 [INFO] Orphaned snapshots found: 2
2025-11-13 16:41:31,441 [INFO] Detailed results written to aws_cleanup_results_1763052091.json
```

Example JSON Report (aws_cleanup_results_1731509421.json)
```
{
  "stopped_instances_found": [],
  "volumes_found": [],
  "amis_found": [
    "ami-0a4982e85f786a114",
    "ami-0abb5e1126e036bc1",
  ],
  "deregister_amis": [
    {
      "ImageId": "ami-0a4982e85f786a114",
      "Deregistered": "DryRun",
      "SnapshotResults": [
        {
          "SnapshotId": "snap-05de73277a198be2e",
          "Action": "DryRun"
        }
      ]
    },
    {
      "ImageId": "ami-0abb5e1126e036bc1",
      "Deregistered": "DryRun",
      "SnapshotResults": [
        {
          "SnapshotId": "snap-0ca53f223852e99b0",
          "Action": "DryRun"
        }
      ]
    }
  ],
  "orphaned_snapshots_found": [
    "snap-08a6f1b764b06b786",
    "snap-0a91ea3840c459668"
  ],
  "delete_snapshots": [
    {
      "SnapshotId": "snap-08419a4db609d5e0d",
      "Action": "DryRun"
    },
    {
      "SnapshotId": "snap-0a91ea3840c459668",
      "Action": "DryRun"
    }
  ]
}
```

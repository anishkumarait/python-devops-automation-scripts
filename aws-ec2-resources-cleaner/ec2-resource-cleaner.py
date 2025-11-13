#!/usr/bin/env python3

import os
import sys
import argparse
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import time
from dateutil import parser as dateparser

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

# ---------------------------
# Logging configuration
# ---------------------------
LOG_FILE = "aws_cleanup.log"
logger = logging.getLogger("aws_cleanup")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)
console = logging.StreamHandler(sys.stdout)
console.setFormatter(fmt)
logger.addHandler(console)

# ---------------------------
# Utility helpers
# ---------------------------
def now_utc():
    return datetime.now(timezone.utc)

def parse_aws_time(timestr):
    # AWS returns ISO8601-ish strings; use dateutil parser for robustness
    return dateparser.parse(timestr) if isinstance(timestr, str) else timestr

def age_in_days(dt):
    return (now_utc() - dt).days

def safe_boto_client(service, region, profile=None):
    session_args = {}
    if profile:
        session_args['profile_name'] = profile
    session = boto3.Session(**session_args) if session_args else boto3.Session()
    return session.client(service, region_name=region), session.resource(service, region_name=region)

# ---------------------------
# Core cleanup operations
# ---------------------------
class Cleaner:
    def __init__(self, region, profile=None, retention_days=30, dry_run=True,
                 exclude_tags=None, exclude_ids=None, max_workers=10):
        self.region = region
        self.profile = profile
        self.retention_days = retention_days
        self.dry_run = dry_run
        self.exclude_tags = exclude_tags or {}  # dict: {Key: Value} or Value==None to only check existence
        self.exclude_ids = set(exclude_ids or [])
        self.max_workers = max_workers

        # boto3 clients/resources
        self.ec2_client, self._ = safe_boto_client('ec2', region, profile)
        # Using the client primarily; some operations may use resource
        self.ec2_resource = boto3.Session(profile_name=profile).resource('ec2', region_name=region) if profile else boto3.resource('ec2', region_name=region)

    def _is_excluded_by_tags(self, tags):
        """
        tags: list of dicts [{'Key':..., 'Value':...}, ...]
        exclude_tags: dict like {'DoNotDelete': None, 'Environment': 'prod'}
        """
        if not self.exclude_tags:
            return False
        if not tags:
            return False
        tag_map = {t['Key']: t.get('Value') for t in tags}
        for k, v in self.exclude_tags.items():
            if k in tag_map:
                if v is None:
                    return True
                if tag_map[k] == v:
                    return True
        return False

    def _is_excluded_id(self, resource_id):
        return resource_id in self.exclude_ids

    # -------- EC2 Instances ----------
    def find_stopped_instances(self):
        """Find stopped instances older than retention_days."""
        logger.info("Scanning for stopped EC2 instances...")
        instances_to_terminate = []
        try:
            paginator = self.ec2_client.get_paginator('describe_instances')
            filters = [{'Name': 'instance-state-name', 'Values': ['stopped', 'stopping']}]
            page_iter = paginator.paginate(Filters=filters)
            for page in page_iter:
                for reservation in page.get('Reservations', []):
                    for inst in reservation.get('Instances', []):
                        instance_id = inst['InstanceId']
                        state = inst['State']['Name']
                        launch_time = inst.get('LaunchTime')  # timezone-aware
                        # We consider 'stopped' age since state transition might be more relevant; try to use StateTransitionReason? Not always present.
                        # Use LaunchTime as fallback — conservative approach.
                        if self._is_excluded_id(instance_id) or self._is_excluded_by_tags(inst.get('Tags', [])):
                            logger.debug(f"Excluded instance {instance_id} by tag/id.")
                            continue
                        # Calculate age from LaunchTime — conservative
                        age = age_in_days(launch_time) if launch_time else None
                        logger.debug(f"Instance {instance_id} state={state}, launch_time={launch_time}, age_days={age}")
                        if age is not None and age >= self.retention_days:
                            instances_to_terminate.append({'InstanceId': instance_id, 'LaunchTime': launch_time})
            logger.info(f"Found {len(instances_to_terminate)} stopped instances older than {self.retention_days} days.")
            return instances_to_terminate
        except ClientError as e:
            logger.error(f"Error describing instances: {e}")
            return []

    def terminate_instances(self, instance_ids):
        """Terminate EC2 instances (batched)"""
        if not instance_ids:
            return []
        logger.info(f"{'Dry-run: would terminate' if self.dry_run else 'Terminating'} {len(instance_ids)} instances.")
        results = []
        # use concurrency for many instances
        def _terminate_batch(batch):
            try:
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would terminate: {batch}")
                    return {'Terminated': batch}
                resp = self.ec2_client.terminate_instances(InstanceIds=batch)
                logger.info(f"Terminate response: {resp.get('TerminatingInstances')}")
                return resp
            except ClientError as e:
                logger.error(f"Failed terminating {batch}: {e}")
                return {'Error': str(e)}
        # chunk into batches of 10 (API limit)
        CHUNK = 10
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = []
            for i in range(0, len(instance_ids), CHUNK):
                batch = instance_ids[i:i + CHUNK]
                futures.append(ex.submit(_terminate_batch, batch))
            for fut in as_completed(futures):
                results.append(fut.result())
        return results

    # -------- EBS Volumes ----------
    def find_unattached_volumes(self):
        """Find available (status=available) volumes older than retention_days and not excluded."""
        logger.info("Scanning for unattached EBS volumes...")
        volumes_to_delete = []
        try:
            paginator = self.ec2_client.get_paginator('describe_volumes')
            page_iter = paginator.paginate(Filters=[{'Name': 'status', 'Values': ['available']}])
            for page in page_iter:
                for v in page.get('Volumes', []):
                    vol_id = v['VolumeId']
                    create_time = v.get('CreateTime') or v.get('CreateTime')  # should exist
                    if self._is_excluded_id(vol_id) or self._is_excluded_by_tags(v.get('Tags', [])):
                        logger.debug(f"Excluded volume {vol_id}")
                        continue
                    age = age_in_days(create_time) if create_time else None
                    logger.debug(f"Volume {vol_id} age_days={age}")
                    if age is not None and age >= self.retention_days:
                        volumes_to_delete.append({'VolumeId': vol_id, 'CreateTime': create_time})
            logger.info(f"Found {len(volumes_to_delete)} unattached volumes older than {self.retention_days} days.")
            return volumes_to_delete
        except ClientError as e:
            logger.error(f"Error describing volumes: {e}")
            return []

    def delete_volume(self, volume_id):
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would delete volume {volume_id}")
                return {'VolumeId': volume_id, 'Action': 'DryRun'}
            resp = self.ec2_client.delete_volume(VolumeId=volume_id)
            logger.info(f"Deleted volume {volume_id} resp={resp}")
            return {'VolumeId': volume_id, 'Action': 'Deleted'}
        except ClientError as e:
            logger.error(f"Failed deleting volume {volume_id}: {e}")
            return {'VolumeId': volume_id, 'Error': str(e)}

    # -------- AMIs & Snapshots ----------
    def find_old_amis(self):
        """Find AMIs owned by self older than retention; returns list of dicts with ImageId, CreationDate, BlockDeviceMappings"""
        logger.info("Scanning for old AMIs owned by self...")
        try:
            account_id = self.ec2_client.describe_account_attributes(AttributeNames=['default-vpc'])  # cheap call to ensure credentials valid
        except Exception:
            pass
        images = []
        try:
            # Only images owned by self (self account)
            resp = self.ec2_client.describe_images(Owners=['self'])
            for img in resp.get('Images', []):
                img_id = img['ImageId']
                creation = parse_aws_time(img.get('CreationDate'))
                if self._is_excluded_id(img_id) or self._is_excluded_by_tags(img.get('Tags', [])):
                    logger.debug(f"Excluded AMI {img_id}")
                    continue
                age = age_in_days(creation) if creation else None
                if age is not None and age >= self.retention_days:
                    images.append({'ImageId': img_id, 'CreationDate': creation, 'Name': img.get('Name'), 'BlockDeviceMappings': img.get('BlockDeviceMappings', [])})
            logger.info(f"Found {len(images)} AMIs older than {self.retention_days} days.")
            return images
        except ClientError as e:
            logger.error(f"Error describing images: {e}")
            return []

    def deregister_ami_and_delete_snapshots(self, image):
        """
        Deregister an AMI and delete associated EBS snapshots referenced by its block device mappings.
        image: dict with 'ImageId' and 'BlockDeviceMappings' etc.
        """
        img_id = image['ImageId']
        snapshots = []
        # extract snapshot ids from BlockDeviceMappings
        for bdm in image.get('BlockDeviceMappings', []):
            ebs = bdm.get('Ebs')
            if ebs and 'SnapshotId' in ebs:
                snapshots.append(ebs['SnapshotId'])
        logger.info(f"AMI {img_id} has {len(snapshots)} associated snapshot(s).")

        results = {'ImageId': img_id, 'Deregistered': False, 'SnapshotResults': []}

        # deregister AMI
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would deregister AMI {img_id}")
                results['Deregistered'] = 'DryRun'
            else:
                self.ec2_client.deregister_image(ImageId=img_id)
                logger.info(f"Deregistered AMI {img_id}")
                results['Deregistered'] = True
        except ClientError as e:
            logger.error(f"Failed to deregister AMI {img_id}: {e}")
            results['Deregistered'] = str(e)

        # attempt delete associated snapshots
        for snap in snapshots:
            try:
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would delete snapshot {snap} (associated with AMI {img_id})")
                    results['SnapshotResults'].append({'SnapshotId': snap, 'Action': 'DryRun'})
                else:
                    self.ec2_client.delete_snapshot(SnapshotId=snap)
                    logger.info(f"Deleted snapshot {snap} (associated with AMI {img_id})")
                    results['SnapshotResults'].append({'SnapshotId': snap, 'Action': 'Deleted'})
            except ClientError as e:
                logger.error(f"Failed to delete snapshot {snap}: {e}")
                results['SnapshotResults'].append({'SnapshotId': snap, 'Error': str(e)})
        return results

    def find_orphaned_snapshots(self):
        """
        Find snapshots owned by self that are not referenced by any AMI and older than retention_days.
        Caution: this may include snapshots used for other purposes; ensure exclusion tags are in place.
        """
        logger.info("Scanning for orphaned snapshots owned by self...")
        snapshots_to_delete = []
        try:
            # get all snapshots owned by self
            paginator = self.ec2_client.get_paginator('describe_snapshots')
            page_iter = paginator.paginate(OwnerIds=['self'])
            # build a set of snapshot ids referenced by images (block device mappings)
            owned_images = self.ec2_client.describe_images(Owners=['self']).get('Images', [])
            referenced_snaps = set()
            for img in owned_images:
                for bdm in img.get('BlockDeviceMappings', []):
                    ebs = bdm.get('Ebs')
                    if ebs and 'SnapshotId' in ebs:
                        referenced_snaps.add(ebs['SnapshotId'])

            for page in page_iter:
                for s in page.get('Snapshots', []):
                    snap_id = s['SnapshotId']
                    start_time = parse_aws_time(s['StartTime'])
                    if snap_id in referenced_snaps:
                        logger.debug(f"Snapshot {snap_id} is referenced by an AMI; skipping.")
                        continue
                    if self._is_excluded_id(snap_id) or self._is_excluded_by_tags(s.get('Tags', [])):
                        logger.debug(f"Excluded snapshot {snap_id}")
                        continue
                    age = age_in_days(start_time) if start_time else None
                    if age is not None and age >= self.retention_days:
                        snapshots_to_delete.append({'SnapshotId': snap_id, 'StartTime': start_time})
            logger.info(f"Found {len(snapshots_to_delete)} orphaned snapshots older than {self.retention_days} days.")
            return snapshots_to_delete
        except ClientError as e:
            logger.error(f"Error describing snapshots: {e}")
            return []

    def delete_snapshot(self, snapshot_id):
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would delete snapshot {snapshot_id}")
                return {'SnapshotId': snapshot_id, 'Action': 'DryRun'}
            self.ec2_client.delete_snapshot(SnapshotId=snapshot_id)
            logger.info(f"Deleted snapshot {snapshot_id}")
            return {'SnapshotId': snapshot_id, 'Action': 'Deleted'}
        except ClientError as e:
            logger.error(f"Failed deleting snapshot {snapshot_id}: {e}")
            return {'SnapshotId': snapshot_id, 'Error': str(e)}

    # -------- Orchestration ----------
    def run(self):
        logger.info(f"Starting cleanup: region={self.region}, retention_days={self.retention_days}, dry_run={self.dry_run}")
        results = {}

        # 1) stopped instances
        stopped = self.find_stopped_instances()
        results['stopped_instances_found'] = [i['InstanceId'] for i in stopped]
        if stopped:
            ids = [i['InstanceId'] for i in stopped]
            results['terminate_instances'] = self.terminate_instances(ids)

        # 2) unattached volumes
        volumes = self.find_unattached_volumes()
        results['volumes_found'] = [v['VolumeId'] for v in volumes]
        if volumes:
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = {ex.submit(self.delete_volume, v['VolumeId']): v['VolumeId'] for v in volumes}
                vol_results = []
                for fut in as_completed(futures):
                    vol_results.append(fut.result())
                results['delete_volumes'] = vol_results

        # 3) old AMIs
        amis = self.find_old_amis()
        results['amis_found'] = [a['ImageId'] for a in amis]
        if amis:
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = {ex.submit(self.deregister_ami_and_delete_snapshots, a): a['ImageId'] for a in amis}
                ami_results = []
                for fut in as_completed(futures):
                    ami_results.append(fut.result())
                results['deregister_amis'] = ami_results

        # 4) orphaned snapshots
        snaps = self.find_orphaned_snapshots()
        results['orphaned_snapshots_found'] = [s['SnapshotId'] for s in snaps]
        if snaps:
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = {ex.submit(self.delete_snapshot, s['SnapshotId']): s['SnapshotId'] for s in snaps}
                snap_results = []
                for fut in as_completed(futures):
                    snap_results.append(fut.result())
                results['delete_snapshots'] = snap_results

        logger.info("Cleanup run complete.")
        return results

# ---------------------------
# CLI and example execution
# ---------------------------
def parse_args():
    p = argparse.ArgumentParser(description="AWS resource cleanup utility (EC2, EBS, AMI, snapshots).")
    p.add_argument('--region', '-r', required=True, help="AWS region (e.g., us-east-1)")
    p.add_argument('--profile', '-p', help="AWS profile name (optional)")
    p.add_argument('--days', '-d', type=int, default=30, help="Retention window in days (default: 30)")
    p.add_argument('--execute', action='store_true', help="Actually perform deletions. If omitted, script runs in dry-run mode.")
    p.add_argument('--exclude-tag', action='append', help="Exclude resources with tag Key or Key=Value (can be repeated). Example: DoNotDelete or Environment=prod")
    p.add_argument('--exclude-id', action='append', help="Exclude specific resource IDs (InstanceId, VolumeId, SnapshotId, ImageId). Can be repeated.")
    p.add_argument('--max-workers', type=int, default=10, help="Max concurrent workers for deletion (default: 10)")
    return p.parse_args()

def parse_exclude_tags(list_of_tag_strs):
    """Convert ['DoNotDelete','Environment=prod'] -> {'DoNotDelete': None, 'Environment':'prod'}"""
    result = {}
    if not list_of_tag_strs:
        return result
    for t in list_of_tag_strs:
        if '=' in t:
            k, v = t.split('=', 1)
            result[k] = v
        else:
            result[t] = None
    return result

def main():
    args = parse_args()
    exclude_tags = parse_exclude_tags(args.exclude_tag)
    exclude_ids = args.exclude_id or []

    cleaner = Cleaner(region=args.region,
                      profile=args.profile,
                      retention_days=args.days,
                      dry_run=not args.execute,
                      exclude_tags=exclude_tags,
                      exclude_ids=exclude_ids,
                      max_workers=args.max_workers)
    results = cleaner.run()

    # Summarize
    logger.info("Summary (high level):")
    logger.info(f"Stopped instances found: {len(results.get('stopped_instances_found', []))}")
    logger.info(f"Volumes found: {len(results.get('volumes_found', []))}")
    logger.info(f"AMIs found: {len(results.get('amis_found', []))}")
    logger.info(f"Orphaned snapshots found: {len(results.get('orphaned_snapshots_found', []))}")

    # Save detailed results to file for auditing
    out_path = f"aws_cleanup_results_{int(time.time())}.json"
    try:
        import json
        with open(out_path, 'w') as fh:
            json.dump(results, fh, default=str, indent=2)
        logger.info(f"Detailed results written to {out_path}")
    except Exception as e:
        logger.error(f"Failed writing detailed results: {e}")

if __name__ == "__main__":
    main()

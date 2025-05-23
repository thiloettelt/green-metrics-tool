#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import faulthandler
faulthandler.enable(file=sys.__stderr__)  # will catch segfaults and write to stderr

import os
import pprint
import argparse

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

from lib.global_config import GlobalConfig
from lib.db import DB
from lib.job.base import Job
from lib import utils
from lib import error_helpers

"""
    This file schedules new Watchlist items by inserting jobs in the jobs table
"""

def schedule_watchlist_item():
    query = """
        SELECT
            id, name, repo_url, branch, filename, machine_id, user_id, schedule_mode, last_marker,
            DATE(last_scheduled) >= DATE(NOW()) as "scheduled_today",
            DATE(last_scheduled) >= DATE(NOW() - INTERVAL '7 DAYS') as "scheduled_last_week"
        FROM watchlist
       """
    data = DB().fetch_all(query)

    for [item_id, name, repo_url, branch, filename, machine_id, user_id, schedule_mode, last_marker, scheduled_today, scheduled_last_week] in data:
        print(f"Watchlist item is on {schedule_mode} schedule", repo_url, branch, filename, machine_id)

        if schedule_mode == 'one-off':
            raise ValueError('Watchlist item with "one-off" schedule mode should never be in table!')

        if schedule_mode == 'daily':
            if not scheduled_today:
                print('\nWatchlist item was not scheduled today', scheduled_today)
                DB().query('UPDATE watchlist SET last_scheduled = NOW() WHERE id = %s', params=(item_id,))
                Job.insert('run', user_id=user_id, name=name, url=repo_url, email=None, branch=branch, filename=filename, machine_id=machine_id)
                print('\tInserted')
        elif schedule_mode == 'weekly':
            if not scheduled_last_week:
                print('\tWatchlist item was not scheduled in last 7 days', scheduled_last_week)
                DB().query('UPDATE watchlist SET last_scheduled = NOW() WHERE id = %s', params=(item_id,))
                Job.insert('run', user_id=user_id, name=name, url=repo_url, email=None, branch=branch, filename=filename, machine_id=machine_id)
                print('\tInserted')
        elif schedule_mode in ['tag', 'tag-variance']:
            last_marker_new = utils.get_repo_last_marker(repo_url, 'tags')
            print('Last marker is', last_marker, ' - Current maker is', last_marker_new)
            if last_marker == last_marker_new:
                continue
            amount = 3 if 'variance' in schedule_mode else 1
            for _ in range(0,amount):
                Job.insert('run', user_id=user_id, name=name, url=repo_url, email=None, branch=branch, filename=filename, machine_id=machine_id)
                print('Updating Hash', last_marker_new)
                DB().query('UPDATE watchlist SET last_marker = %s WHERE id = %s', params=(last_marker_new, item_id, ))

        elif schedule_mode in ['commit', 'commit-variance']:
            last_marker_new = utils.get_repo_last_marker(repo_url, 'commits')
            print('Last marker is', last_marker, ' - Current maker is', last_marker_new)
            if last_marker == last_marker_new:
                continue
            amount = 3 if 'variance' in schedule_mode else 1
            for _ in range(0,amount):
                print('Updating Hash', last_marker_new)
                Job.insert('run', user_id=user_id, name=name, url=repo_url, email=None, branch=branch, filename=filename, machine_id=machine_id)
                DB().query('UPDATE watchlist SET last_marker = %s WHERE id = %s', params=(last_marker_new, item_id, ))

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('mode', choices=['show', 'schedule'], help='Show will show all Watchlist items. Schedule will insert a job.')

        args = parser.parse_args()  # script will exit if arguments not present

        if args.mode == 'show':
            show_query = """
                SELECT
                    w.id, w.name, w.repo_url,
                    (SELECT STRING_AGG(t.name, ', ' ) FROM unnest(w.categories) as elements
                            LEFT JOIN categories as t on t.id = elements) as categories,
                    w.branch, w.filename, m.description, w.last_scheduled, w.schedule_mode,
                    w.created_at, w.updated_at
                FROM watchlist as w
                LEFT JOIN machines as m on m.id = w.machine_id
                ORDER BY w.repo_url ASC
            """
            show_data = DB().fetch_all(show_query, fetch_mode='dict')
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(show_data)

        else:
            schedule_watchlist_item()

    except Exception as exc: # pylint: disable=broad-except
        error_helpers.log_error(f'Processing in {__file__} failed.', exception=exc, machine=GlobalConfig().config['machine']['description'])

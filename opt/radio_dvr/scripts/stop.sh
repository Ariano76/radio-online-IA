#!/bin/bash

sudo systemctl stop radio_scheduler.service

sudo systemctl status radio_scheduler.service --no-pager
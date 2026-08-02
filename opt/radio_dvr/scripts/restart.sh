#!/bin/bash

sudo systemctl restart radio_scheduler.service

sudo systemctl status radio_scheduler.service --no-pager
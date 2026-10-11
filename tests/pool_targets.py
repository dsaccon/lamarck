import os
import time


def echo(job):
    return {"v": job["v"]}


def hang(job):
    time.sleep(60)


def crash(job):
    os._exit(3)


def boom(job):
    raise ValueError("boom")

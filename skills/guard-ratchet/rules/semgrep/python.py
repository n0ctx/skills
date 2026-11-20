import time
import requests
import httpx

# ---------------------------------------------------------------- unbounded-retry
def retry_cases():
    # ruleid: gr.py.unbounded-retry
    while True:
        try:
            work()
        except Exception:
            time.sleep(1)

    # ruleid: gr.py.unbounded-retry
    while True:
        if ready:
            try:
                work()
            except OSError as e:
                log(e)

    # ok: gr.py.unbounded-retry
    while True:
        try:
            work()
            break
        except Exception:
            time.sleep(1)

    # ok: gr.py.unbounded-retry
    while True:
        try:
            return work()
        except Exception:
            attempts += 1
            if attempts > 5:
                raise

    # ok: gr.py.unbounded-retry
    while True:
        try:
            work()
        except Exception:
            if attempts > 5:
                sys.exit(1)

    # ok: gr.py.unbounded-retry
    while True:
        msg = queue.get()
        handle(msg)

    # ok: gr.py.unbounded-retry
    while attempts < 5:
        try:
            work()
        except Exception:
            attempts += 1

# ---------------------------------------------------------------- swallowed-exception
def swallow_cases():
    # ruleid: gr.py.swallowed-exception
    try:
        risky()
    except:
        pass

    # ruleid: gr.py.swallowed-exception
    try:
        risky()
    except Exception:
        pass

    # ruleid: gr.py.swallowed-exception
    try:
        risky()
    except Exception as e:
        ...

    for x in xs:
        # ruleid: gr.py.swallowed-exception
        try:
            risky(x)
        except BaseException:
            continue

    # ruleid: gr.py.swallowed-exception
    try:
        risky()
    except ValueError:
        raise
    except Exception:
        pass

    # ok: gr.py.swallowed-exception
    try:
        risky()
    except Exception:
        logger.exception("risky failed")

    # ok: gr.py.swallowed-exception
    try:
        risky()
    except Exception:
        logger.warning("ignored")
        pass

    # ok: gr.py.swallowed-exception
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    # ok: gr.py.swallowed-exception
    try:
        risky()
    except (KeyError, ValueError):
        pass

    # ok: gr.py.swallowed-exception
    try:
        risky()
    except Exception:
        raise

# ---------------------------------------------------------------- requests-without-timeout
def requests_cases(url, kw):
    # ruleid: gr.py.requests-without-timeout
    requests.get(url)
    # ruleid: gr.py.requests-without-timeout
    requests.post(url, json={"a": 1}, headers=H)
    # ruleid: gr.py.requests-without-timeout
    requests.request("GET", url)
    # ruleid: gr.py.requests-without-timeout
    requests.get(url, timeout=None)
    # ruleid: gr.py.requests-without-timeout
    httpx.get(url, timeout=None)
    # ok: gr.py.requests-without-timeout
    requests.get(url, timeout=10)
    # ok: gr.py.requests-without-timeout
    requests.post(url, json={}, timeout=(3.05, 27))
    # ok: gr.py.requests-without-timeout
    requests.get(url, **kw)
    # ok: gr.py.requests-without-timeout
    httpx.get(url)
    # ok: gr.py.requests-without-timeout
    httpx.get(url, timeout=5.0)
    # ok: gr.py.requests-without-timeout
    session.get(url)
    # ok: gr.py.requests-without-timeout
    requests.utils.quote(url)

# ---------------------------------------------------------------- blocking-sleep-in-async
async def sleep_cases():
    # ruleid: gr.py.blocking-sleep-in-async
    time.sleep(1)

    if cond:
        # ruleid: gr.py.blocking-sleep-in-async
        time.sleep(0.5)

    # ok: gr.py.blocking-sleep-in-async
    await asyncio.sleep(1)

    def worker():
        # ok: gr.py.blocking-sleep-in-async
        time.sleep(1)

    await asyncio.to_thread(worker)

def make_handler():
    async def handler():
        # ruleid: gr.py.blocking-sleep-in-async
        time.sleep(1)
    return handler

def sync_sleep():
    # ok: gr.py.blocking-sleep-in-async
    time.sleep(1)

# ---------------------------------------------------------------- subprocess-shell-injection
def shell_cases(name, path, n):
    # ruleid: gr.py.subprocess-shell-injection
    subprocess.run(f"ls {path}", shell=True)
    # ruleid: gr.py.subprocess-shell-injection
    subprocess.check_output("grep %s file.txt" % name, shell=True)
    # ruleid: gr.py.subprocess-shell-injection
    subprocess.Popen("cat {}".format(path), shell=True, stdout=PIPE)
    # ruleid: gr.py.subprocess-shell-injection
    os.system("rm -rf " + path)
    # ruleid: gr.py.subprocess-shell-injection
    os.popen(f"git log -n {n}")
    # ok: gr.py.subprocess-shell-injection
    subprocess.run("ls -la", shell=True)
    # ok: gr.py.subprocess-shell-injection
    subprocess.run(["ls", path])
    # ok: gr.py.subprocess-shell-injection
    subprocess.run(f"ls {path}")
    # ok: gr.py.subprocess-shell-injection
    subprocess.run(f"ls {shlex.quote(path)}", shell=True)
    # ok: gr.py.subprocess-shell-injection
    os.system("echo " + "hello")
    # ok: gr.py.subprocess-shell-injection
    os.system("ls " + "-la " + "/tmp")
    # ok: gr.py.subprocess-shell-injection
    os.system(f"echo done")
    # ok: gr.py.subprocess-shell-injection
    os.system(COMMAND)

# ---------------------------------------------------------------- sql-string-build
def sql_cases(cursor, conn, user_id, table, name):
    # ruleid: gr.py.sql-string-build
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    # ruleid: gr.py.sql-string-build
    cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)
    # ruleid: gr.py.sql-string-build
    cursor.execute("DELETE FROM {} WHERE id = 1".format(table))
    # ruleid: gr.py.sql-string-build
    conn.execute("UPDATE users SET name = '" + name + "' WHERE id = 1")
    # ruleid: gr.py.sql-string-build
    cursor.executemany(f"INSERT INTO {table} (a, b) VALUES (?, ?)", rows)
    # ruleid: gr.py.sql-string-build
    session.execute(text(f"SELECT * FROM {table}"))
    # ok: gr.py.sql-string-build
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    # ok: gr.py.sql-string-build
    cursor.execute("SELECT * FROM users WHERE id = ?", [user_id])
    # ok: gr.py.sql-string-build
    cursor.execute("SELECT * FROM users " + "WHERE active = 1")
    # ok: gr.py.sql-string-build
    cursor.execute("SELECT * FROM users WHERE active = 1")
    # ok: gr.py.sql-string-build
    cursor.execute(QUERY, (user_id,))
    # ok: gr.py.sql-string-build
    executor.execute(f"retry {name} later")
    # ok: gr.py.sql-string-build
    session.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})

# ---------------------------------------------------------------- unsafe-deserialization
def deser_cases(f, blob):
    # ruleid: gr.py.unsafe-deserialization
    pickle.load(f)
    # ruleid: gr.py.unsafe-deserialization
    pickle.loads(blob)
    # ruleid: gr.py.unsafe-deserialization
    yaml.load(f)
    # ruleid: gr.py.unsafe-deserialization
    yaml.load(f, Loader=yaml.Loader)
    # ruleid: gr.py.unsafe-deserialization
    yaml.load(f, Loader=yaml.UnsafeLoader)
    # ruleid: gr.py.unsafe-deserialization
    yaml.load(f, yaml.Loader)
    # ruleid: gr.py.unsafe-deserialization
    yaml.unsafe_load(f)
    # ruleid: gr.py.unsafe-deserialization
    marshal.loads(blob)
    # ok: gr.py.unsafe-deserialization
    yaml.load(f, Loader=yaml.SafeLoader)
    # ok: gr.py.unsafe-deserialization
    yaml.load(f, Loader=yaml.CSafeLoader)
    # ok: gr.py.unsafe-deserialization
    yaml.load(f, yaml.SafeLoader)
    # ok: gr.py.unsafe-deserialization
    yaml.safe_load(f)
    # ok: gr.py.unsafe-deserialization
    pickle.dumps(blob)
    # ok: gr.py.unsafe-deserialization
    json.loads(blob)
    # ok: gr.py.unsafe-deserialization
    yaml.dump(blob)

# ---------------------------------------------------------------- tls-verify-disabled
def tls_cases(url, ca):
    # ruleid: gr.py.tls-verify-disabled
    requests.get(url, verify=False, timeout=5)
    # ruleid: gr.py.tls-verify-disabled
    requests.post(url, json={}, verify=False, timeout=5)
    # ruleid: gr.py.tls-verify-disabled
    httpx.Client(verify=False)
    # ruleid: gr.py.tls-verify-disabled
    httpx.get(url, verify=False)
    # ruleid: gr.py.tls-verify-disabled
    ctx = ssl._create_unverified_context()
    # ruleid: gr.py.tls-verify-disabled
    ssl._create_default_https_context = ssl._create_unverified_context
    # ruleid: gr.py.tls-verify-disabled
    session.verify = False
    # ok: gr.py.tls-verify-disabled
    requests.get(url, verify=True, timeout=5)
    # ok: gr.py.tls-verify-disabled
    requests.get(url, verify=ca, timeout=5)
    # ok: gr.py.tls-verify-disabled
    requests.get(url, verify="/etc/ssl/ca.pem", timeout=5)
    # ok: gr.py.tls-verify-disabled
    httpx.Client(verify=ssl.create_default_context())
    # ok: gr.py.tls-verify-disabled
    self.verify = False
    # ok: gr.py.tls-verify-disabled
    ctx = ssl.create_default_context()

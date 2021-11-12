import hashlib
import os
import random
import re


def get_temp_filepath(ext=None):
    while True:
        hash = '%032x' % random.getrandbits(128)
        path = "/tmp/" + hash
        if ext != None:
            path += "." + ext
        if not os.path.exists(path):
            break
    return path


def check_response(resp, content_types, status_codes=200):
    passed = False
    if resp.status_code >= 200 and resp.status_code < 300 and content_types is not None:
        if type(content_types) == list:
            for content_type in content_types:
                if content_type in resp.headers['Content-Type']:
                    passed = True
                    break
        else:
            content_type = content_types
            if content_type in resp.headers['Content-Type']:
                passed = True
    else:
        passed = True
    if not passed:
        return False
    passed = False
    if type(status_codes) == list:
        for status_code in status_codes:
            if resp.status_code == status_code:
                passed = True
                break
    else:
        status_code = status_codes
        if resp.status_code == status_code:
            passed = True
    return passed


def get_valid_fullurl(path, recruit_page_url):
    if re.match("^(http://|https://).*", path):
        full_url_path = path
    else:
        assert re.match(".*/$", recruit_page_url) is None
        assert re.match("^/.*", path) is not None
        full_url_path = recruit_page_url + path
    return full_url_path



def get_hash_of(*args):
    concatenated = ""
    for arg in args:
        concatenated += str(arg)
    return hashlib.sha256(concatenated.encode()).hexdigest()

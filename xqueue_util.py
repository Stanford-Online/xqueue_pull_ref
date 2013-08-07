##### Much of this is adopted (copy-and-pasted) from                #####
##### https://github.com/edx/edx-ora/blob/master/controller/urls.py #####

import requests
import urlparse
import logging
import json
import settings
import project_urls

log = logging.getLogger(__name__)

def xqueue_login():
    session = requests.session()
    xqueue_login_url = urlparse.urljoin(settings.XQUEUE_INTERFACE['url'], project_urls.XqueueURLs.log_in)
    (success, xqueue_msg) = login(
                                  session,
                                  xqueue_login_url,
                                  settings.XQUEUE_INTERFACE['django_auth']['username'],
                                  settings.XQUEUE_INTERFACE['django_auth']['password'],
                                  )
    
    return session


def login(session, url, username, password):
    """
        Login to given url with given username and password.
        Use given request session (requests.session)
    """
    
    log.debug("Trying to login to {0} with user: {1} and pass {2}".format(url,username,password))
    response = session.post(url,
                            {'username': username,
                            'password': password,
                            }
                            )
    
    if response.status_code == 500 and url.endswith("/"):
        response = session.post(url[:-1],
                                {'username': username,
                                'password': password,
                                }
                                )
    
    
    response.raise_for_status()
    log.debug("login response from %r: %r", url, response.json)
    (success, msg) = parse_xreply(response.content)
    return success, msg


def parse_xreply(xreply):
    """
        Parse the reply from xqueue. Messages are JSON-serialized dict:
        { 'return_code': 0 (success), 1 (fail)
        'content': Message from xqueue (string)
        }
    """
    
    try:
        xreply = json.loads(xreply)
    except ValueError:
        error_message =  "Could not parse xreply."
        log.error(error_message)
        return (False, error_message)
    
    #This is to correctly parse xserver replies and internal success/failure messages
    if 'return_code' in xreply:
        return_code = (xreply['return_code']==0)
        content = xreply['content']
    elif 'success' in xreply:
        return_code = xreply['success']
        content=xreply
    else:
        return False, "Cannot find a valid success or return code."
    
    if return_code not in [True,False]:
        return (False, 'Invalid return code.')
    
    
    return return_code, content


def parse_xobject(xobject, queue_name):
    """
        Parse a queue object from xqueue:
        { 'return_code': 0 (success), 1 (fail)
        'content': Message from xqueue (string)
        }
        """
    try:
        xobject = json.loads(xobject)
        
        header = json.loads(xobject['xqueue_header'])
        header.update({'queue_name': queue_name})
        body = json.loads(xobject['xqueue_body'])
        files = json.loads(xobject['xqueue_files'])
        
        content = {'xqueue_header': json.dumps(header),
            'xqueue_body': json.dumps(body),
            'xqueue_files': json.dumps(files)
        }
    except ValueError:
        error_message = "Unexpected reply from server."
        log.error(error_message)
        return (False, error_message)
    
    return True, content

def _http_get(session, url, data=None):
    """
        Send an HTTP get request:
        session: requests.session object.
        url : url to send request to
        data: optional dictionary to send
        """
    if data is None:
        data = {}
    try:
        r = session.get(url, params=data)
    except requests.exceptions.ConnectionError:
        error_message = "Cannot connect to server."
        log.error(error_message)
        return (False, error_message)
    
    if r.status_code == 500 and url.endswith("/"):
        r = session.get(url[:-1], params=data)
    
    if r.status_code not in [200]:
        return (False, 'Unexpected HTTP status code [%d]' % r.status_code)
    if hasattr(r, "text"):
        text = r.text
    elif hasattr(r, "content"):
        text = r.content
    else:
        error_message = "Could not get response from http object."
        log.exception(error_message)
        return False, error_message
    return parse_xreply(text)


def _http_post(session, url, data, timeout):
    '''
        Contact grading controller, but fail gently.
        Takes following arguments:
        session - requests.session object
        url - url to post to
        data - dictionary with data to post
        timeout - timeout in settings
        
        Returns (success, msg), where:
        success: Flag indicating successful exchange (Boolean)
        msg: Accompanying message; Controller reply when successful (string)
        '''
    
    try:
        r = session.post(url, data=data, timeout=timeout, verify=False)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        error_message = 'Could not connect to server at %s in timeout=%f' % (url, timeout)
        log.error(error_message)
        return (False, error_message)
            
    if r.status_code == 500 and url.endswith("/"):
        r = session.post(url[:-1], data=data, timeout=timeout, verify=False)
    
    if r.status_code not in [200]:
        error_message = "Server %s returned status_code=%d' % (url, r.status_code)"
        log.error(error_message)
        return (False, error_message)
    
    if hasattr(r, "text"):
        text = r.text
    elif hasattr(r, "content"):
        text = r.content
    else:
        error_message = "Could not get response from http object."
        log.exception(error_message)
        return False, error_message
    
    return (True, text)

def post_results_to_xqueue(session, header, body):
    """
        Post the results from a grader back to xqueue.
        Input:
        session - a requests session that is logged in to xqueue
        header - xqueue header.  Dict containing keys submission_key and submission_id
        body - xqueue body.  Arbitrary dict.
        """
    request = {
        'xqueue_header': header,
        'xqueue_body': body,
    }
    
    (success, msg) = _http_post(session, settings.XQUEUE_INTERFACE['url'] + project_urls.XqueueURLs.put_result, request,
                                settings.REQUESTS_TIMEOUT)
    
    return success, msg

def create_xqueue_header_and_body(submission_id, submission_key, correct, score, feedback, grader_id):
    xqueue_header = {
        'submission_id': submission_id,
        'submission_key': submission_key,
    }
    
    xqueue_body = {
        'msg': feedback,
        'correct': correct,
        'score': score,
        'grader_id' : grader_id,
    }
    
    return xqueue_header, xqueue_body





"""
This is a minimum working example of a Matchmaker Exchange server.
It is intended strictly as a useful reference, and should not be
used in a production setting.
"""

from __future__ import with_statement, division, unicode_literals

import logging
import json
import requests
from flask import Flask, request, after_this_request, jsonify, render_template, url_for
from flask_negotiate import consumes, produces
from collections import defaultdict
from werkzeug.exceptions import BadRequest
from werkzeug.datastructures import Headers

from .compat import urlopen, Request
from .auth import auth_token_required
from .models import MatchRequest
from .schemas import validate_request, validate_response, ValidationError


API_MIME_TYPE = 'application/vnd.ga4gh.matchmaker.v1.0+json'

# Global flask application
app = Flask(__name__.split('.')[0], template_folder='templates')
app.secret_key = 'MySuperSecretSecretKey'
app.config['DEBUG'] = True

# Logger
logger = logging.getLogger(__name__)

@app.route('/', methods=['POST', 'GET'])
def index():

    data = {}
    if request.method == 'POST':
        features = []
        if request.form.get("features"):
            for hpo_feature in request.form.get("features").split(','):
                features.append( {"id":hpo_feature} )

        gene_features = []
        if request.form.get("genomic_features"):
            #split by comma and create list of objects (genes for now)
            for gene_id in request.form.get("genomic_features").split(','):
                gene_features.append( { "gene":{"id":gene_id} } )

        patient_query= {
            "patient": {
                "id": request.form.get("patients_id"),
                "contact" : {
                    "name": request.form.get("name"),
                    "href": "mailto:"+request.form.get("email")
                },
                "features": features,
                "genomicFeatures": gene_features,
            }
        }

        #add initial query to data object
        data['json_query']=json.dumps(patient_query)

        #convert python boolean to something similar to json boolean:
        #patient_query["patient"]["test"] = str(patient_query["patient"]["test"]).lower()

        headers = Headers()
        headers = {'Content-Type': 'application/vnd.ga4gh.matchmaker.v1.0+json', 'Accept': 'application/vnd.ga4gh.matchmaker.v1.0+json', 'X-Auth-Token': request.form.get("token")}

        server_return = requests.post(
            'http://localhost:8000/v1/match',
            headers = headers,
            data = json.dumps(patient_query)
        )

        # get json response:
        json_response = server_return.json()
        data['result']=json_response

    return render_template('search.html', **data)


@app.route('/v1/match', methods=['POST'])
@consumes(API_MIME_TYPE, 'application/json')
@produces(API_MIME_TYPE)
@auth_token_required()
def match():
    """Return patients similar to the query patient"""
    @after_this_request
    def add_header(response):
        response.headers['Content-Type'] = API_MIME_TYPE
        return response

    try:
        logger.info("Getting flask request data")
        request_json = request.get_json(force=True)
    except BadRequest:
        error = jsonify(message='Invalid request JSON')
        error.status_code = 400
        return error

    try:
        logger.info("Validate request syntax")
        validate_request(request_json)
    except ValidationError as e:
        error = jsonify(message='Request does not conform to API specification',
                        request=request_json)
        error.status_code = 422
        return error

    logger.info("Parsing query")
    request_obj = MatchRequest.from_api(request_json)

    logger.info("Finding similar patients")
    response_obj = request_obj.match(n=5)

    logger.info("Serializing response")
    response_json = response_obj.to_api()

    try:
        logger.info("Validating response syntax")
        validate_response(response_json)
    except ValidationError as e:
        # log to console and return response anyway
        logger.error('Response does not conform to API specification:\n{}\n\nResponse:\n{}'.format(e, response_json))

    return jsonify(response_json)

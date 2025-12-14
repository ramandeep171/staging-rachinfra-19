import logging
import json
import base64
import requests
import phonenumbers
import datetime
import time
import hashlib
from odoo.http import request, JsonRPCDispatcher, Response

from odoo.http import request
from odoo import http, modules

_logger = logging.getLogger(__name__)
import werkzeug.datastructures
import werkzeug.exceptions
import werkzeug.local
import werkzeug.routing
import werkzeug.security
import werkzeug.wrappers
import werkzeug.wsgi
from werkzeug.urls import URL, url_parse, url_encode, url_quote
from werkzeug.exceptions import (HTTPException, BadRequest, Forbidden,
                                 NotFound, InternalServerError)
import io


def _response_inherit(self, result=None, error=None):
    # request_id = jsonrequest.get('id')
    # status = 200
    response = ''
    if error is not None:
        response = error
        status = error.pop('http_status', 200)
    if result is not None:
        response = result

    return request.make_json_response(response)

def make_json_response_inherit(self, data, headers=None, cookies=None, status=200):
    """ Helper for JSON responses, it json-serializes ``data`` and
    sets the Content-Type header accordingly if none is provided.

    :param data: the data that will be json-serialized into the response body
    :param int status: http status code
    :param List[(str, str)] headers: HTTP headers to set on the response
    :param collections.abc.Mapping cookies: cookies to set on the client
    :rtype: :class:`~odoo.http.Response`
    """
    data = ''

    headers = werkzeug.datastructures.Headers(headers)
    headers['Content-Length'] = len(data)
    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json; charset=utf-8'

    return self.make_response(data, headers.to_wsgi_list(), cookies, status)

def make_response(self, data, headers=None, cookies=None, status=200):
    """ Helper for non-HTML responses, or HTML responses with custom
    response headers or cookies.

    While handlers can just return the HTML markup of a page they want to
    send as a string if non-HTML data is returned they need to create a
    complete response object, or the returned data will not be correctly
    interpreted by the clients.

    :param str data: response body
    :param int status: http status code
    :param headers: HTTP headers to set on the response
    :type headers: ``[(name, value)]``
    :param collections.abc.Mapping cookies: cookies to set on the client
    :returns: a response object.
    :rtype: :class:`~odoo.http.Response`
    """
    response = Response(data, status=status, headers=headers)
    if cookies:
        for k, v in cookies.items():
            response.set_cookie(k, v)
    return response


def _json_response_inherit(self, result=None, error=None):
    response = ''
    if error is not None:
        response = error
    if result is not None:
        response = result
    mime = 'application/json'
    body = ''
    return Response(
        body, status=error and error.pop('http_status', 200) or 200,
        headers=[('Content-Type', mime), ('Content-Length', len(body))]
    )


class WhatsappBase(http.Controller):

    @http.route('/whatsapp/response/message', type='json', auth='public')
    def whatsapp_response(self):
        # Get messages response from webhook
        # For first time compare mobile number is exists in res partner using chat id if exists create whatsapp message & add chat_id in res partner
        # If mobile number is not exists in res partner then create new partner
        # If get reply for specific message that stored in odoo then add res_id,res_model,whatsapp instance,whatsapp provider in whatsapp messages
        response_dict = json.loads(request.httprequest.data)
        _logger.info("Webhook 1msg response dict %s: ", str(response_dict))
        if response_dict.get('messages'):
            whatsapp_message_obj = request.env['whatsapp.messages']
            for whatsapp_message_dict in response_dict.get('messages'):
                message_dict = {}
                if whatsapp_message_dict.get('quotedMsgId'):
                    whatsapp_messages_id = whatsapp_message_obj.sudo().search([('message_id', '=', whatsapp_message_dict.get('quotedMsgId'))])
                    whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')],
                                                                                       limit=1)
                    if whatsapp_messages_id and whatsapp_messages_id.partner_id:
                        message_dict.update({
                            'partner_id': whatsapp_messages_id.partner_id.id,
                            'model': whatsapp_messages_id.model,
                            'res_id': whatsapp_messages_id.res_id,
                            'whatsapp_instance_id': whatsapp_instance_id.id,
                            'whatsapp_message_provider': whatsapp_instance_id.provider
                        })
                    message_dict = self.create_message_dict(whatsapp_message_dict, message_dict)

                elif not whatsapp_message_dict.get('quotedMsgId') and not whatsapp_message_dict.get('fromMe'):
                    if '@c.us' in whatsapp_message_dict['chatId']:  # @c.us is for normal conversation & @g.us is for group conversation
                        # Creating Partner in odoo
                        res_partner_obj = request.env['res.partner']
                        res_partner_id = res_partner_obj.sudo().search([('chatId', '=', whatsapp_message_dict['chatId'])], limit=1)
                        if res_partner_id:
                            message_dict.update({'partner_id': res_partner_id.id, 'model': 'res.partner', 'res_id': res_partner_id.id})
                        else:
                            country_with_mobile = self.sanitized_country_mobile_from_chat_id(whatsapp_message_dict.get('chatId'))
                            res_partner_id = self.create_res_partner_against_whatsapp(whatsapp_message_dict['chatId'], whatsapp_message_dict.get('senderName'),
                                                                                      country_with_mobile[0], country_with_mobile[1])
                            message_dict.update({'partner_id': res_partner_id, 'model': 'res.partner', 'res_id': res_partner_id})

                        # Creating whatsapp message in odoo
                        message_dict = self.create_message_dict(whatsapp_message_dict, message_dict)
                whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')], limit=1)
                if whatsapp_instance_id and message_dict :
                    message_dict.update({'whatsapp_instance_id': whatsapp_instance_id.id, 'whatsapp_message_provider': whatsapp_instance_id.provider})
                whatsapp_message_id = whatsapp_message_obj.sudo().search(
                    [('message_id', '=', whatsapp_message_dict.get('id')), ('whatsapp_instance_id', '=', whatsapp_instance_id.id)])
                if not whatsapp_message_id and message_dict:
                    # If message in document format then create attachment, whatsapp message
                    whatsapp_message_id = whatsapp_message_obj.sudo().create(message_dict)
                    _logger.info("Whatsapp Message created in odoo Whatsapp message id %s: ", str(whatsapp_message_id))
                    if whatsapp_message_id and whatsapp_message_dict.get('type') == 'document':
                        data_base64 = base64.b64encode(requests.get(whatsapp_message_dict.get('body').strip()).content)
                        message_attachment_dict = {
                            'name': whatsapp_message_dict.get('caption'),
                            'datas': data_base64,
                            'type': 'binary',
                            'res_model': 'whatsapp.messages',
                            'res_id': whatsapp_message_id.id
                        }
                        attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                        _logger.info("Attachment is created in odoo when creating whatsapp message attachment id %s: ", str(attachment_id))
                        whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
                elif whatsapp_message_id and message_dict:
                    # If message in document format then create attachment, whatsapp message
                    whatsapp_message_id.sudo().write(message_dict)
                    _logger.info("Whatsapp message updated in odoo whatsapp message id %s: ", str(whatsapp_message_id))
                    if whatsapp_message_id and whatsapp_message_dict.get('type') == 'document':
                        data_base64 = base64.b64encode(requests.get(whatsapp_message_dict.get('body').strip()).content)
                        message_attachment_dict = {
                            'name': whatsapp_message_dict.get('caption'),
                            'datas': data_base64,
                            'type': 'binary',
                            'res_model': 'whatsapp.messages',
                            'res_id': whatsapp_message_id.id
                        }
                        attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                        _logger.info("Attachment is created in odoo when updating whatsapp message attachment id %s: ", str(attachment_id))
                        whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
        return True

    def create_res_partner_against_whatsapp(self, chat_id, sender_name, country_code, mobile):
        # Creation of partner
        partner_dict = {}
        res_country_id = request.env['res.country'].sudo().search([('phone_code', '=', country_code)], limit=1)
        if res_country_id:
            partner_dict['country_id'] = res_country_id.id
        partner_dict.update({'name': sender_name, 'mobile': str(country_code) + str(mobile), 'chatId': chat_id})
        res_partner_id = request.env['res.partner'].sudo().create(partner_dict)
        _logger.info("Res partner is created in odoo partner id %s: ", str(res_partner_id.id))
        return res_partner_id.id

    def create_message_dict(self, whatsapp_message_dict, message_dict):
        # creation of whatsapp message dict
        message_dict.update({
            'name': whatsapp_message_dict.get('body'),
            'message_id': whatsapp_message_dict.get('id'),
            'to': whatsapp_message_dict.get('chatName') if whatsapp_message_dict.get('fromMe') else 'To Me',
            'chatId': whatsapp_message_dict.get('chatId'),
            'type': whatsapp_message_dict.get('type'),
            'senderName': whatsapp_message_dict.get('senderName'),
            'chatName': whatsapp_message_dict.get('chatName'),
            'author': whatsapp_message_dict.get('author'),
            'time': self.convert_epoch_to_unix_timestamp(int(whatsapp_message_dict.get('time'))),
            'state': 'received',
        })
        # if whatsapp message is in image format then update message body
        if whatsapp_message_dict.get('type') == 'image':
            image_data = base64.b64encode(requests.get(whatsapp_message_dict.get('body').strip()).content).replace(b'\n', b'')
            message_dict.update({'message_body': whatsapp_message_dict.get('caption'), 'msg_image': image_data})

        # if whatsapp message is in text,video,audio format then update message body
        if whatsapp_message_dict.get('type') == 'chat' or whatsapp_message_dict.get('type') == 'video' or whatsapp_message_dict.get(
                'type') == 'audio':
            message_dict.update({'message_body': whatsapp_message_dict.get('body')})

        # if whatsapp message is in document format then update message body
        if whatsapp_message_dict['type'] == 'document':
            message_dict.update({'message_body': whatsapp_message_dict.get('caption')})

        return message_dict

    def convert_epoch_to_unix_timestamp(self, msg_time):
        # convert webhook whatsapp time to local timezone
        formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg_time))
        date_time_obj = datetime.datetime.strptime(formatted_time, '%Y-%m-%d %H:%M:%S')
        return date_time_obj

    def sanitized_country_mobile_from_chat_id(self, whatsapp_id):
        # Santized country & mobile from chat id
        mobile_country_code = ''
        if '@' in whatsapp_id:
            mobile_country_code = phonenumbers.parse('+' + (whatsapp_id.split('@'))[0], None)
        else:
            mobile_country_code = phonenumbers.parse('+' + whatsapp_id, None)
        country_code = mobile_country_code.country_code
        res_country_id = request.env['res.country'].sudo().search([('phone_code', '=', country_code)], limit=1)
        return country_code, mobile_country_code.national_number
    
    def sanitized_country_mobile_from_meta_chat_id(self, whatsapp_id):
        # Santized country & mobile from chat id
        mobile_country_code = phonenumbers.parse('+' + whatsapp_id, None)
        country_code = mobile_country_code.country_code
        number = '+'+ str(country_code)
        return number, mobile_country_code.national_number

    @http.route('/gupshup/response/message', type='json', auth='public')
    def gupshup_whatsapp_response(self):
        _logger.info("\n---------------------In whatsapp integration controller base-----------------------")
        data = json.loads(request.httprequest.data)
        _logger.info("data from gupshup %s: ", str(data))
        if data.get('type') == 'message' and data['payload'] and data['payload'].get('sender'):
            whatsapp_message_obj = request.env['whatsapp.messages']
            whatsapp_messages_dict = {}
            data_payload = data['payload']
            if data_payload.get('context'):     # If quoted message id from response
                whatsapp_messages_id = whatsapp_message_obj.sudo().search([('message_id', '=', data_payload['context'].get('gsId'))])
                whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')],
                                                                                   limit=1)
                if whatsapp_messages_id and whatsapp_messages_id.partner_id:
                    whatsapp_messages_dict.update({
                        'partner_id': whatsapp_messages_id.partner_id.id,
                        'model': whatsapp_messages_id.model,
                        'res_id': whatsapp_messages_id.res_id,
                        'whatsapp_instance_id': whatsapp_instance_id.id,
                        'whatsapp_message_provider': whatsapp_instance_id.provider
                    })
                    whatsapp_messages_dict = self.gupshup_create_whatsapp_message_dict(data, whatsapp_messages_dict)
            else:
                res_partner_obj = request.env['res.partner']
                country_with_mobile = self.sanitized_country_mobile_from_chat_id(data_payload.get('sender').get('phone'))
                res_partner_id = res_partner_obj.sudo().search([('phone', '=', str(country_with_mobile[0])+str(country_with_mobile[1]))], limit=1)
                if not res_partner_id:
                    res_partner_id = self.gupshup_create_res_partner_against_whatsapp(data_payload.get('sender').get('name'), country_with_mobile[0], country_with_mobile[1])
                whatsapp_messages_dict.update({'partner_id': res_partner_id.id, 'model': 'res.partner', 'res_id': res_partner_id.id})

                whatsapp_messages_dict = self.gupshup_create_whatsapp_message_dict(data, whatsapp_messages_dict)
            whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')],
                                                                               limit=1)
            if whatsapp_instance_id and whatsapp_messages_dict:
                whatsapp_messages_dict.update({'whatsapp_instance_id': whatsapp_instance_id.id, 'whatsapp_message_provider': whatsapp_instance_id.provider})
            whatsapp_message_id = whatsapp_message_obj.sudo().search([('message_id', '=', data_payload.get('id')), ('whatsapp_instance_id', '=', whatsapp_instance_id.id)])
            if whatsapp_message_id and whatsapp_messages_dict:
                whatsapp_message_id.sudo().write(whatsapp_messages_dict)
                _logger.info("Whatsapp message updated in odoo from gupshup whatsapp message id %s: ", str(whatsapp_message_id.id))
                if whatsapp_message_id and data_payload.get('type') == 'file':
                    data_base64 = base64.b64encode(requests.get(data_payload.get('payload').get('url').strip()).content)
                    message_attachment_dict = {
                        'name': data_payload.get('payload').get('caption'),
                        'datas': data_base64,
                        'type': 'binary',
                        'res_model': 'whatsapp.messages',
                        'res_id': whatsapp_message_id.id
                    }
                    attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                    _logger.info("Attachment is created in odoo when updating whatsapp message from gupshup attachment id %s: ", str(attachment_id.id))
                    whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
            elif not whatsapp_message_id and whatsapp_messages_dict:
                whatsapp_message_id = whatsapp_message_obj.sudo().create(whatsapp_messages_dict)
                _logger.info("Whatsapp Message created in odoo from gupshup Whatsapp message id %s: ", str(whatsapp_message_id.id))
                if whatsapp_message_id and data_payload.get('type') == 'file':
                    data_base64 = base64.b64encode(requests.get(data_payload.get('payload').get('url').strip()).content)
                    message_attachment_dict = {
                        'name': data_payload.get('payload').get('caption'),
                        'datas': data_base64,
                        'type': 'binary',
                        'res_model': 'whatsapp.messages',
                        'res_id': whatsapp_message_id.id
                    }
                    attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                    _logger.info("Attachment is created in odoo when creating whatsapp message from gupshup attachment id %s: ", str(attachment_id))
                    whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
        _response_inherit(data)
        # request._json_response = _json_response_inherit.__get__(request, JsonRequest)

        return True

    def gupshup_create_whatsapp_message_dict(self, webhook_dict, whatsapp_messages_dict):
        # creation of whatsapp message dict
        webhook_payload = webhook_dict['payload']
        whatsapp_messages_dict.update({
            'message_id': webhook_payload.get('id'),
            'to': 'To Me',
            'chatId': webhook_dict.get('chatId'),
            'type': webhook_payload.get('type'),
            'senderName': webhook_payload.get('sender').get('name'),
            'chatName': webhook_payload.get('sender').get('phone'),
            'author': webhook_payload.get('sender').get('phone'),
            'time': self.gupshup_convert_epoch_to_unix_timestamp(webhook_dict.get('timestamp')),
            'state': 'received',
        })
        # if whatsapp message is in image format then update message body
        if webhook_payload.get('type') == 'image' or webhook_payload.get('type') == 'audio' or webhook_payload.get('type') == 'video' or webhook_payload.get('type') == 'file':
            image_data = base64.b64encode(requests.get(webhook_payload.get('payload').get('url').strip()).content).replace(b'\n', b'')
            whatsapp_messages_dict.update({'msg_image': image_data})
            if webhook_payload.get('payload').get('caption'):
                whatsapp_messages_dict.update({'message_body': webhook_payload.get('payload').get('caption')})
        if webhook_payload.get('type') == 'text':
            whatsapp_messages_dict.update({'message_body': webhook_payload.get('payload').get('text')})
        return whatsapp_messages_dict

    def gupshup_create_res_partner_against_whatsapp(self, sender_name, country_code, mobile):
        # Creation of partner
        partner_dict = {}
        res_country_id = request.env['res.country'].sudo().search([('phone_code', '=', country_code)], limit=1)
        if res_country_id:
            partner_dict['country_id'] = res_country_id.id
        partner_dict.update({'name': sender_name, 'mobile': str(country_code) + str(mobile)})
        res_partner_id = request.env['res.partner'].sudo().create(partner_dict)
        _logger.info("Res partner is created in odoo from gupshup res_partner id %s: ", str(res_partner_id.id))
        return res_partner_id

    def gupshup_convert_epoch_to_unix_timestamp(self, msg_time):
        current_date_time = datetime.datetime.fromtimestamp(int(msg_time) / 1000)
        return current_date_time
    
    def create_res_partner_against_meta_whatsapp(self,number,sender_name, country_code, mobile):
        # Creation of partner
        partner_dict = {}
        res_country_id = request.env['res.country'].sudo().search([('phone_code', '=', country_code)], limit=1)
        if res_country_id:
            partner_dict['country_id'] = res_country_id.id
        partner_dict.update({'name': sender_name, 'phone': str(country_code) + str(mobile),'chatId': str(number)})
        res_partner_id = request.env['res.partner'].sudo().create(partner_dict)
        _logger.info("Res partner is created in odoo from meta res_partner id %s: ", str(res_partner_id.id))
        return res_partner_id
    
    
    def meta_create_message_dict(self, whatsapp_message_dict, message_dict,data):
        # creation of whatsapp message dict
        message_dict.update({
            'name': whatsapp_message_dict.get('text').get('body') if whatsapp_message_dict.get('text') else '',
            'message_id': whatsapp_message_dict.get('id'),
            # 'to': whatsapp_message_dict.get('chatName') if whatsapp_message_dict.get('fromMe') else 'To Me',
            'chatId': whatsapp_message_dict.get('from'),
            'type': whatsapp_message_dict.get('type'),
            'senderName': data.get('entry')[0].get('changes')[0].get('value').get('contacts')[0].get('profile').get('name'),
            'chatName': whatsapp_message_dict.get('from'),
            # 'author': whatsapp_message_dict.get('author'),
            'time': self.convert_epoch_to_unix_timestamp(int(whatsapp_message_dict.get('timestamp'))),
            'state': 'received',
        })
        # if whatsapp message is in image format then update message body
        if whatsapp_message_dict.get('type') == 'image':
            mime_type = data['entry'][0]['changes'][0]['value']['messages'][0]['image']['mime_type']
            media_id = data['entry'][0]['changes'][0]['value']['messages'][0]['image']['id']
            # caption = attachment["caption"]
            whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('whatsapp_meta_phone_number_id', 'like', '%' + str(data.get('entry')[0].get('changes')[0].get('value').get('metadata').get('phone_number_id')))], limit=1)
            url = "https://graph.facebook.com/v16.0/{}".format(media_id)
            page_access_token = whatsapp_instance_id.whatsapp_meta_api_token
            headers = {
            "Authorization": "Bearer {}".format(page_access_token)
            }
            image = requests.get(url.strip(), headers=headers).json()
            image_datas = base64.b64encode(requests.get(image["url"], headers=headers).content)
            message_dict.update({'message_body': '', 'msg_image':  image_datas})

        # if whatsapp message is in text,video,audio format then update message body
        # if whatsapp_message_dict.get('type') == 'text' or whatsapp_message_dict.get('type') == 'video' or whatsapp_message_dict.get(
        #         'type') == 'audio':
        #     message_dict.update({'message_body': whatsapp_message_dict.get('text').get('body')})
        if whatsapp_message_dict.get('type') == 'text':
            message_dict.update({'message_body': whatsapp_message_dict.get('text').get('body')})
        if whatsapp_message_dict.get('type') == 'video':
            message_dict.update({'message_body': whatsapp_message_dict.get('video').get('body')})
        if whatsapp_message_dict.get('type') == 'audio':
            message_dict.update({'message_body': whatsapp_message_dict.get('audio').get('body')})
        # if whatsapp_message_dict.get('type') == 'audio/ogg; codecs=opus':
        #     message_dict.update({'message_body': whatsapp_message_dict.get('audio/ogg; codecs=opus').get('body')})

        # if whatsapp message is in document format then update message body
        if whatsapp_message_dict['type'] == 'document':

            message_dict.update({'message_body': whatsapp_message_dict.get('document').get('filename')})

        return message_dict


    @http.route('/whatsapp_meta/response/message',type='http',auth='public',methods=['GET', 'POST'], website=True,csrf=False)
    def whatsapp_meta_webhook(self):
        if request.httprequest.method == 'GET':
            _logger.info("In whatsapp integration controller verification")
            whatsapp_instance_id = request.env['whatsapp.instance'].get_whatsapp_instance()
            verify_token = whatsapp_instance_id.whatsapp_meta_webhook_token

            VERIFY_TOKEN = verify_token

            if 'hub.mode' in request.httprequest.args:
                mode = request.httprequest.args.get('hub.mode')
            if 'hub.verify_token' in request.httprequest.args:
                token = request.httprequest.args.get('hub.verify_token')

            if 'hub.challenge' in request.httprequest.args:
                challenge = request.httprequest.args.get('hub.challenge')

            if 'hub.mode' in request.httprequest.args and 'hub.verify_token' in request.httprequest.args:
                mode = request.httprequest.args.get('hub.mode')
                token = request.httprequest.args.get('hub.verify_token')

                if mode == 'subscribe' and token == VERIFY_TOKEN:

                    challenge = request.httprequest.args.get('hub.challenge')
                    return http.Response(challenge, status=200)

                    # return challenge, 200
                else:
                    return http.Response('ERROR', status=403)

        elif request.httprequest.method == 'POST':
            _logger.info("Handling POST request for WhatsApp webhook event")

            payload = json.loads(request.httprequest.data)
            _logger.info(f"Received WhatsApp webhook payload: {json.dumps(payload, indent=2)}")

            if 'entry' in payload:
                for entry in payload['entry']:
                    for change in entry.get('changes', []):
                        field = change.get('field')
                        value = change.get('value')
                        statuses = value.get('statuses', [])

                        for status_data in statuses:
                            message_id = status_data.get('id')  # The ID of the message whose status has been updated
                            status = status_data.get('status')  # The status of the message: sent, delivered, read
                            timestamp = status_data.get('timestamp')  # The timestamp of when the status changed
                            recipient_id = status_data.get('recipient_id')  # The recipient's phone number

                            _logger.info("Processing message ID: %s, Status: %s, Timestamp: %s, Recipient: %s",
                                         message_id, status, timestamp, recipient_id)

                            # Find the corresponding whatsapp.message record in Odoo
                            whatsapp_message = request.env['whatsapp.messages'].sudo().search(
                                [('message_id', '=', message_id)], limit=1)

                            if whatsapp_message:
                                # Update the status of the message in Odoo
                                whatsapp_message.sudo().write({
                                    'msg_status': status,
                                })
                                _logger.info("Updated message status in Odoo for message ID %s to %s", message_id,
                                             status)
                            else:
                                _logger.error("Message ID %s not found in Odoo", message_id)

                        # ✅ Check if Template Status Update Event
                        if field == 'message_template_status_update':
                            _logger.info("Handling Template Status Update Event")
                            template_id = value.get('message_template_id')
                            event = value.get('event')
                            reason = value.get('reason', '')

                            _logger.info(f"Template ID '{template_id}' status updated to '{event}' (Reason: {reason})")

                            if template_id and event:
                                whatsapp_template = request.env['whatsapp.templates'].sudo().search([
                                    ('template_id', '=', template_id)
                                ], limit=1)

                                if whatsapp_template:
                                    whatsapp_template.sudo().write({
                                        'approval_state': event,
                                    })
                                    _logger.info(f"Updated template '{template_id}' approval_state to '{event}'")
                                else:
                                    _logger.warning(f"Template ID '{template_id}' not found in Odoo database")
                            else:
                                _logger.warning("Template ID or event missing in the webhook payload")



            # return 'SOMETHING', 200
        data = json.loads(request.httprequest.data)
        _logger.info("Webhook meta api response dict %s: ", str(data))
        if data.get('entry')[0].get('changes')[0].get('value').get('messages'):
            whatsapp_message_obj = request.env['whatsapp.messages']
            for whatsapp_message_dict in data.get('entry')[0].get('changes')[0].get('value').get('messages'):
                message_dict = {}
                if whatsapp_message_dict.get('context'):
                    whatsapp_messages_id = whatsapp_message_obj.sudo().search([('message_id', '=', whatsapp_message_dict.get('id'))])
                    whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')],
                                                                                       limit=1)
                    if whatsapp_messages_id and whatsapp_messages_id.partner_id:
                        message_dict.update({
                            'partner_id': whatsapp_messages_id.partner_id.id,
                            'model': whatsapp_messages_id.model,
                            'res_id': whatsapp_messages_id.res_id,
                            'whatsapp_instance_id': whatsapp_instance_id.id,
                            'whatsapp_message_provider': whatsapp_instance_id.provider
                        })
                    message_dict = self.meta_create_message_dict(whatsapp_message_dict, message_dict,data)
                else:
                        res_partner_obj = request.env['res.partner']
                        res_partner_id = res_partner_obj.sudo().search([('chatId', '=', whatsapp_message_dict.get('from'))], limit=1)
                        if res_partner_id:
                            message_dict.update({'partner_id': res_partner_id.id, 'model': 'res.partner', 'res_id': res_partner_id.id})
                        else:
                            country_with_mobile = self.sanitized_country_mobile_from_meta_chat_id(whatsapp_message_dict.get('from'))
                            res_partner_id = self.create_res_partner_against_meta_whatsapp(whatsapp_message_dict.get('from'),data.get('entry')[0].get('changes')[0].get('value').get('contacts')[0].get('profile').get('name'),
                                                                                    country_with_mobile[0], country_with_mobile[1])
                            message_dict.update({'partner_id': res_partner_id.id, 'model': 'res.partner', 'res_id': res_partner_id.id})

                        # Creating whatsapp message in odoo
                        message_dict = self.meta_create_message_dict(whatsapp_message_dict, message_dict,data)
                whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search([('status', '!=', 'disable')],
                                                                                   limit=1)
                if whatsapp_instance_id and message_dict :
                    message_dict.update({'whatsapp_instance_id': whatsapp_instance_id.id, 'whatsapp_message_provider': whatsapp_instance_id.provider})
                whatsapp_message_id = whatsapp_message_obj.sudo().search(
                    [('message_id', '=', whatsapp_message_dict.get('id')), ('whatsapp_instance_id', '=', whatsapp_instance_id.id)])
                if not whatsapp_message_id and message_dict:
                    # If message in document format then create attachment, whatsapp message
                    whatsapp_message_id = whatsapp_message_obj.sudo().create(message_dict)
                    _logger.info("Whatsapp Message created in odoo Whatsapp message id %s: ", str(whatsapp_message_id))
                    if whatsapp_message_id and whatsapp_message_dict.get('type') == 'document':
                        mime_type = data['entry'][0]['changes'][0]['value']['messages'][0]['document']['mime_type']
                        media_id = data['entry'][0]['changes'][0]['value']['messages'][0]['document']['id']
                        url = "https://graph.facebook.com/v16.0/{}".format(media_id)
                        page_access_token = whatsapp_instance_id.whatsapp_meta_api_token
                        headers = {
                        "Authorization": "Bearer {}".format(page_access_token)
                        }
                        image = requests.get(url.strip(), headers=headers).json()
                        image_datas = base64.b64encode(requests.get(image["url"], headers=headers).content)
                        message_attachment_dict = {
                            'name': whatsapp_message_dict.get('document').get('filename'),
                            'datas': image_datas,
                            'type': 'binary',
                            'res_model': 'whatsapp.messages',
                            'res_id': whatsapp_message_id.id
                        }
                        attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                        _logger.info("Attachment is created in odoo when creating whatsapp message attachment id %s: ", str(attachment_id))
                        whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
                elif whatsapp_message_id and message_dict:
                    # If message in document format then create attachment, whatsapp message
                    whatsapp_message_id.sudo().write(message_dict)
                    _logger.info("Whatsapp message updated in odoo whatsapp message id %s: ", str(whatsapp_message_id))
                    if whatsapp_message_id and whatsapp_message_dict.get('type') == 'document':
                        mime_type = data['entry'][0]['changes'][0]['value']['messages'][0]['document']['mime_type']
                        media_id = data['entry'][0]['changes'][0]['value']['messages'][0]['document']['id']
                        url = "https://graph.facebook.com/v16.0/{}".format(media_id)
                        page_access_token = whatsapp_instance_id.whatsapp_meta_api_token
                        headers = {
                        "Authorization": "Bearer {}".format(page_access_token)
                        }
                        image = requests.get(url.strip(), headers=headers).json()
                        image_datas = base64.b64encode(requests.get(image["url"], headers=headers).content)
                        # data_base64 = base64.b64encode(whatsapp_message_dict.get('document').get('sha256').encode('utf-8'))
                        message_attachment_dict = {
                            'name': whatsapp_message_dict.get('document').get('filename'),
                            'datas': image_datas,
                            'type': 'binary',
                            'res_model': 'whatsapp.messages',
                            'res_id': whatsapp_message_id.id
                        }
                        attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                        _logger.info("Attachment is created in odoo when updating whatsapp message attachment id %s: ", str(attachment_id))
                        whatsapp_message_id.sudo().write({'attachment_id': attachment_id.id})
                
        # return True

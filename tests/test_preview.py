import json
import os
import uuid
from base64 import b64decode
from io import BytesIO
from unittest.mock import Mock, patch, ANY

from flask import url_for
from flask_weasyprint import HTML
from functools import partial
import pytest

from notifications_utils.s3 import S3ObjectNotFound

from app import LOGOS
from app.preview import get_logo, get_pdf_redis_key
from app.transformation import Logo
from werkzeug.exceptions import BadRequest

from tests.conftest import set_config
from tests.pdf_consts import one_page_pdf


@pytest.fixture
def view_letter_template(client, auth_header, preview_post_body):
    """
    Makes a post to the view_letter_template endpoint
    usage examples:

    resp = post()
    resp = post('pdf')
    resp = post('pdf', json={...})
    resp = post('pdf', headers={...})
    """
    return lambda filetype='pdf', data=preview_post_body, headers=auth_header: (
        client.post(
            url_for('preview_blueprint.view_letter_template', filetype=filetype),
            data=json.dumps(data),
            headers={
                'Content-type': 'application/json',
                **headers
            }
        )
    )


@pytest.fixture
def view_letter_template_as_pdf(client, auth_header):
    """
    Makes a post to the view_letter_template endpoint
    usage examples:
    resp = post()
    resp = post("<html></html>")
    resp = post("<html></html>", headers={...})
    """
    return lambda html="<html></html>", headers=auth_header: (
        client.post(
            url_for('preview_blueprint.view_letter_template_as_pdf'),
            data=json.dumps({'html': html}),
            headers={
                'Content-type': 'application/json',
                **headers
            }
        )
    )


@pytest.fixture
def view_letter_template_as_png(client, auth_header):
    """
    Makes a post to the view_letter_template endpoint
    usage examples:
    resp = post()
    resp = post("<html></html>")
    resp = post("<html></html>", headers={...})
    """
    return lambda html="<html></html>", headers=auth_header: (
        client.post(
            url_for('preview_blueprint.view_letter_template_as_png'),
            data=json.dumps({'html': html}),
            headers={
                'Content-type': 'application/json',
                **headers
            }
        )
    )


@pytest.fixture
def print_letter_template(client, auth_header, preview_post_body):
    """
    Makes a post to the view_letter_template endpoint
    usage examples:

    resp = post()
    resp = post('pdf')
    resp = post('pdf', json={...})
    resp = post('pdf', headers={...})
    """
    return lambda data=preview_post_body, headers=auth_header: (
        client.post(
            url_for('preview_blueprint.print_letter_template'),
            data=json.dumps(data),
            headers={
                'Content-type': 'application/json',
                **headers
            }
        )
    )


@pytest.fixture
def print_letter_template_from_html(client, auth_header, preview_post_body):
    """
    Makes a post to the view_letter_template endpoint
    usage examples:

    resp = post()
    resp = post("<html></html>")
    resp = post("<html></html>", headers={...})
    """
    return lambda html="<html></html>", headers=auth_header: (
        client.post(
            url_for('preview_blueprint.print_letter_template_from_html'),
            data=json.dumps({'html': html}),
            headers={
                'Content-type': 'application/json',
                **headers
            }
        )
    )


@pytest.mark.parametrize('filetype', ['pdf', 'png'])
@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Token not-the-actual-token'}])
def test_preview_rejects_if_not_authenticated(client, filetype, headers):
    resp = client.post(
        url_for('preview_blueprint.view_letter_template', filetype=filetype),
        data={},
        headers=headers
    )
    assert resp.status_code == 401


@pytest.mark.parametrize('filetype, mimetype', [
    ('pdf', 'application/pdf'),
    ('png', 'image/png')
])
def test_return_headers_match_filetype(view_letter_template, filetype, mimetype):
    resp = view_letter_template(filetype)

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == mimetype


def test_get_pdf_from_html(
    app,
    mocker,
    view_letter_template_as_pdf,
    mocked_cache_get,
    mocked_cache_set,
):

    resp = view_letter_template_as_pdf()

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.get_data().startswith(b'%PDF-1.5')
    mocked_cache_get.assert_called_once_with(
        'development-template-preview-cache',
        '941efb7368e46b27b937d34b07fc4d41da01b002.pdf'
    )
    assert mocked_cache_set.call_count == 1
    mocked_cache_set.call_args[0][0].seek(0)
    assert mocked_cache_set.call_args[0][0].read() == resp.get_data()
    assert mocked_cache_set.call_args[0][1] == 'eu-west-1'
    assert mocked_cache_set.call_args[0][2] == 'development-template-preview-cache'
    assert mocked_cache_set.call_args[0][3] == '941efb7368e46b27b937d34b07fc4d41da01b002.pdf'


@pytest.mark.parametrize('side_effects, number_of_cache_get_calls, number_of_cache_set_calls', [
    (
        [S3ObjectNotFound({}, ''), S3ObjectNotFound({}, '')],
        2,
        2,
    ),
    (
        [BytesIO(b'\x00'), S3ObjectNotFound({}, '')],
        1,
        0,
    ),
    (
        [S3ObjectNotFound({}, ''), BytesIO(b64decode(one_page_pdf))],
        2,
        1,
    ),
    (
        [BytesIO(b'\x00'), BytesIO(b'\x00')],
        1,
        0,
    ),
])
def test_get_png_from_html(
    app,
    mocker,
    view_letter_template_as_png,
    mocked_cache_get,
    mocked_cache_set,
    side_effects,
    number_of_cache_get_calls,
    number_of_cache_set_calls,
):

    mocked_cache_get.side_effect = side_effects

    resp = view_letter_template_as_png()

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'image/png'
    assert mocked_cache_get.call_count == number_of_cache_get_calls
    assert mocked_cache_set.call_count == number_of_cache_set_calls


def test_return_headers_match_filetype_for_png(view_letter_template_as_png):
    resp = view_letter_template_as_png()
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'image/png'


@pytest.mark.parametrize('filetype, sentence_count, page_number, expected_response_code', [
    ('png', 10, 1, 200),
    ('pdf', 10, 1, 400),
    ('png', 10, 2, 400),
    ('png', 50, 2, 200),
    ('png', 50, 3, 400),
])
def test_get_image_by_page(
    client,
    auth_header,
    filetype,
    sentence_count,
    page_number,
    expected_response_code,
    mocker,
):
    mocked_hide_notify = mocker.patch('app.preview.hide_notify_tag')
    response = client.post(
        url_for('preview_blueprint.view_letter_template', filetype=filetype, page=page_number),
        data=json.dumps({
            'letter_contact_block': '123',
            'template': {
                'id': str(uuid.uuid4()),
                'subject': 'letter subject',
                'content': (
                    'All work and no play makes Jack a dull boy. ' * sentence_count
                ),
                'version': 1
            },
            'values': {},
            'dvla_org_id': '001',
        }),
        headers={
            'Content-type': 'application/json',
            **auth_header
        }
    )
    assert response.status_code == expected_response_code
    assert not mocked_hide_notify.called


def test_letter_template_constructed_properly(preview_post_body, view_letter_template):
    with patch('app.preview.LetterPreviewTemplate', __str__=Mock(return_value='foo')) as mock_template:
        resp = view_letter_template()
        assert resp.status_code == 200

    mock_template.assert_called_once_with(
        preview_post_body['template'],
        values=preview_post_body['values'],
        contact_block=preview_post_body['letter_contact_block'],
        admin_base_url='http://localhost:6013',
        logo_file_name='hm-government.png',
        date=None,
    )


def test_invalid_filetype_404s(view_letter_template):
    resp = view_letter_template(filetype='foo')
    assert resp.status_code == 404


@pytest.mark.parametrize('missing_item', {
    'letter_contact_block', 'values', 'template', 'dvla_org_id'
})
def test_missing_field_400s(view_letter_template, preview_post_body, missing_item):
    preview_post_body.pop(missing_item)

    resp = view_letter_template(data=preview_post_body)

    assert resp.status_code == 400


def test_bad_org_id_400s(view_letter_template, preview_post_body):

    preview_post_body.update({'dvla_org_id': '404'})

    resp = view_letter_template(data=preview_post_body)

    assert resp.status_code == 400


@pytest.mark.parametrize('blank_item', ['letter_contact_block', 'values'])
def test_blank_fields_okay(view_letter_template, preview_post_body, blank_item):
    preview_post_body[blank_item] = None

    with patch('app.preview.LetterPreviewTemplate', __str__=Mock(return_value='foo')) as mock_template:
        resp = view_letter_template(data=preview_post_body)

    assert resp.status_code == 200
    assert mock_template.called is True


def test_date_can_be_passed(view_letter_template, preview_post_body):

    preview_post_body['date'] = '2012-12-12T00:00:00'

    with patch('app.preview.HTML', wraps=HTML) as mock_html:
        resp = view_letter_template(data=preview_post_body)

    assert resp.status_code == 200
    assert '12 December 2012' in mock_html.call_args_list[0][1]['string']


@pytest.mark.parametrize('sentence_count, expected_pages', [
    (10, 1),
    (50, 2),
])
def test_page_count(
    client,
    auth_header,
    sentence_count,
    expected_pages
):
    response = client.post(
        url_for('preview_blueprint.page_count'),
        data=json.dumps({
            'letter_contact_block': '123',
            'template': {
                'id': str(uuid.uuid4()),
                'subject': 'letter subject',
                'content': (
                    'All work and no play makes Jack a dull boy. ' * sentence_count
                ),
                'version': 1
            },
            'values': {},
            'dvla_org_id': '001',
        }),
        headers={
            'Content-type': 'application/json',
            **auth_header
        }
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {'count': expected_pages}


def test_print_letter_returns_200(print_letter_template):
    resp = print_letter_template()

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.headers['X-pdf-page-count'] == '1'
    assert len(resp.get_data()) > 0


def test_print_letter_from_html_returns_200(print_letter_template_from_html):
    resp = print_letter_template_from_html()

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.headers['X-pdf-page-count'] == '1'
    assert len(resp.get_data()) > 0


@pytest.mark.parametrize('dvla_org_id, expected_filename', [
    ('001', 'hm-government.png'),
    ('002', 'opg.png'),
    ('003', 'dwp.png'),
    ('004', 'geo.png'),
    ('005', 'ch.png'),
    ('500', 'hm-land-registry.png'),
    pytest.mark.xfail((500, 'strings_only.png'), raises=BadRequest),
    pytest.mark.xfail(('999', 'doesnt_exist.png'), raises=BadRequest),
])
def test_getting_logos(client, dvla_org_id, expected_filename):
    assert get_logo(dvla_org_id).raster == expected_filename


@pytest.mark.parametrize(
    'logo',
    list(
        LOGOS.values()
    ) + [
        pytest.mark.xfail(Logo('not_real.bmp'), raises=AssertionError)
    ]
)
def test_that_logo_files_exist(logo):
    for filename in (
        logo.raster, logo.vector
    ):
        assert os.path.isfile(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                '..',
                'static', 'images', 'letter-template',
                filename
            )
        )


def test_logo_class():
    assert Logo('dept').raster == 'dept.png'
    assert Logo('dept').vector == 'dept.svg'


@pytest.mark.parametrize('partially_initialised_class', [
    partial(Logo),
    partial(Logo, raster='example.png'),
    partial(Logo, vector='example.svg'),
])
def test_that_logos_only_accept_one_argument(partially_initialised_class):
    with pytest.raises(TypeError):
        partially_initialised_class()


def test_get_set_cached_pdf_none(
        app,
        mocker,
        client,
        auth_header
):
    with set_config(app, 'REDIS_ENABLED', True):

        notification_data = json.dumps({
            'letter_contact_block': '123',
            'template': {
                'id': 1,
                'subject': 'letter subject',
                'content': (
                    'All work and no play makes Jack a dull boy. '
                ),
                'version': 1
            },
            'values': {},
            'dvla_org_id': '001',
        })

        mocked_redis_get = mocker.patch('app.preview.current_app.redis_store.get', return_value=None)
        mocked_redis_set = mocker.patch('app.preview.current_app.redis_store.set')

        response = client.post(
            url_for('preview_blueprint.view_letter_template', filetype='pdf'),
            data=notification_data,
            headers={
                'Content-type': 'application/json',
                **auth_header
            }
        )

        unique_name_dict = {
            'template_id': 1,
            'version': 1,
            'dvla_org_id': '001',
            'letter_contact_block': '123',
            'values': None
        }

        assert response.status_code == 200
        mocked_redis_get.assert_called_once_with(sorted(unique_name_dict.items()))
        mocked_redis_set.assert_called_once_with(sorted(unique_name_dict.items()), ANY, ex=600)


def test_get_cached_pdf(
        app,
        mocker,
        client,
        auth_header
):
    with set_config(app, 'REDIS_ENABLED', True):

        notification_data = json.dumps({
            'letter_contact_block': '123',
            'template': {
                'id': 1,
                'subject': 'letter subject',
                'content': (
                    'All work and no play makes Jack a dull boy. '
                ),
                'version': 1
            },
            'values': {},
            'dvla_org_id': '001',
        })

        mocked_redis_get = mocker.patch('app.preview.current_app.redis_store.get', return_value="qwertyuiop")
        mocked_redis_set = mocker.patch('app.preview.current_app.redis_store.set')

        response = client.post(
            url_for('preview_blueprint.view_letter_template', filetype='pdf'),
            data=notification_data,
            headers={
                'Content-type': 'application/json',
                **auth_header
            }
        )

        assert response.status_code == 200

        unique_name_dict = {
            'template_id': 1,
            'version': 1,
            'dvla_org_id': '001',
            'letter_contact_block': '123',
            'values': None
        }

        mocked_redis_get.assert_called_once_with(sorted(unique_name_dict.items()))
        assert mocked_redis_set.call_count == 0
        assert response.get_data() == b"qwertyuiop"


def test_get_pdf_redis_key(client):
    notification_data = {
        'letter_contact_block': '123',
        'dvla_org_id': '001',
        'template': {
            'id': 1,
            'subject': 'letter subject',
            'content': (
                'All work and no play makes Jack a dull boy. '
            ),
            'version': 1
        },
        'values': {
            'f': ['a', 1, None, False],
            'c': None,
            'd': False,
            'a': 'a',
            'b': 1,
            'e': []
        }
    }

    sorted_list = get_pdf_redis_key(notification_data)
    assert sorted_list == [
        ('dvla_org_id', '001'),
        ('letter_contact_block', '123'),
        ('template_id', 1),
        ('values',
         [
             ('a', 'a'),
             ('b', 1),
             ('c', None),
             ('d', False),
             ('e', []),
             ('f', ['a', 1, None, False])
         ]),
        ('version', 1)]

*** Settings ***
Library    SSHLibrary
Library    String

*** Variables ***
${IMAGE_URL}         ghcr.io/platypuschan/maubot:latest
# The update scenario starts from the last published release of this module;
# test-module-update.sh looks it up in the registry.
${PREVIOUS_IMAGE_URL}    ${EMPTY}
${SCENARIO}          install
${HOST}              maubot.test
${PLUGIN_ID}         io.github.platypuschan.nsci
${module_id}         ${EMPTY}
${web_port}          ${EMPTY}
${admin_password}    ${EMPTY}
${token}             ${EMPTY}
${ADMIN_USER}        admin
${ADMIN_PASSWORD}    Nethesis,1234

*** Keywords ***
Login to cluster-admin
    New Page    https://${NODE_ADDR}/cluster-admin/
    Fill Text    text="Username"    ${ADMIN_USER}
    Click    button >> text="Continue"
    Fill Text    text="Password"    ${ADMIN_PASSWORD}
    Click    button >> text="Log in"
    Wait For Elements State    css=#main-content    visible    timeout=10s

Read allocated web port
    ${port} =    Execute Command    runagent -m ${module_id} printenv TCP_PORT
    ${port} =    Strip String    ${port}
    Should Match Regexp    ${port}    ^[0-9]+$
    Set Suite Variable    ${web_port}    ${port}

Get configuration
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/get-configuration
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    get-configuration failed: ${output}
    &{config} =    Evaluate    json.loads(r'''${output}''')    modules=json
    RETURN    &{config}

Read admin credentials
    &{config} =    Get configuration
    Should Be Equal    ${config.url}    https://${HOST}/_matrix/maubot/
    Should Be Equal    ${config.admin_user}    admin
    Should Not Be Empty    ${config.admin_password}
    Set Suite Variable    ${admin_password}    ${config.admin_password}

Run action
    [Arguments]    ${action}    ${payload}
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/${action} --data '${payload}'
    ...    return_rc=True
    RETURN    ${output}    ${rc}

Configure current module
    [Arguments]    &{extra}
    ${payload} =    Evaluate    json.dumps({"host": $HOST, "http2https": False, "lets_encrypt": False, **$extra})    modules=json
    ${output}    ${rc} =    Run action    configure-module    ${payload}
    Should Be Equal As Integers    ${rc}    0    configure-module failed: ${output}

# curl through Traefik; prints the HTTP status in the last line
Route
    [Arguments]    ${method}    ${path}    @{options}
    ${extra} =    Catenate    @{options}
    ${output}    ${rc} =    Execute Command    curl -sS --max-time 10 --resolve ${HOST}:80:127.0.0.1 -w '\\n\%{http_code}' -X ${method} ${extra} 'http://${HOST}${path}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    curl failed: ${output}
    ${body}    ${status} =    Evaluate    $output.rsplit("\\n", 1)
    RETURN    ${body}    ${status}

Login to maubot
    [Arguments]    ${password}
    ${payload} =    Evaluate    json.dumps({"username": "admin", "password": $password})    modules=json
    ${body}    ${status} =    Route    POST    /_matrix/maubot/v1/auth/login    -H 'Content-Type: application/json'    -d '${payload}'
    RETURN    ${body}    ${status}

maubot accepts the admin login
    ${body}    ${status} =    Login to maubot    ${admin_password}
    Should Be Equal    ${status}    200    login failed: ${body}
    &{login} =    Evaluate    json.loads(r'''${body}''')    modules=json
    Set Suite Variable    ${token}    ${login.token}

Wait until maubot is up
    Wait Until Keyword Succeeds    120 seconds    2 seconds    maubot accepts the admin login

Plugin list
    ${body}    ${status} =    Route    GET    /_matrix/maubot/v1/plugins    -H 'Authorization: Bearer ${token}'
    Should Be Equal    ${status}    200    plugin list failed: ${body}
    RETURN    ${body}

Upload the test plugin
    Put Directory    ${CURDIR}/ci-plugin    /root/ci-plugin
    ${output}    ${rc} =    Execute Command    cd /root/ci-plugin && rm -f /root/ci.mbp && python3 -m zipfile -c /root/ci.mbp maubot.yaml nsci.py
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    building the plugin failed: ${output}
    ${body}    ${status} =    Route    POST    /_matrix/maubot/v1/plugins/upload?allow_override=true    -H 'Authorization: Bearer ${token}'    -H 'Content-Type: application/zip'    --data-binary @/root/ci.mbp
    Should Match Regexp    ${status}    ^20[01]$    upload failed: ${body}
    Should Contain    ${body}    "${PLUGIN_ID}"

Volume path
    [Arguments]    ${path}
    # Used inside sh -c '...': no single quotes here
    RETURN    "$(podman volume inspect --format {{.Mountpoint}} maubot-data)/${path}"

*** Test Cases ***
Add module for ${SCENARIO} scenario
    IF    r'${SCENARIO}' == 'update'
        Set Local Variable    ${install_image}    ${PREVIOUS_IMAGE_URL}
    ELSE
        Set Local Variable    ${install_image}    ${IMAGE_URL}
    END
    ${output}    ${rc} =    Execute Command    add-module ${install_image} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module ${install_image} failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Configure initial module
    Configure current module
    Read allocated web port
    Read admin credentials
    Wait until maubot is up
    IF    r'${SCENARIO}' == 'update'
        # A plugin uploaded before the update must survive it.
        Upload the test plugin
    END

Update module from the previous release
    Skip If    r'${SCENARIO}' != 'update'    only the update scenario updates the module
    Log    Scenario ${SCENARIO} with ${IMAGE_URL}    console=${True}
    # Same request as the Software Center: no forced pull.
    ${output}    ${rc} =    Execute Command    api-cli run update-module --data '{"module_url":"${IMAGE_URL}","instances":["${module_id}"]}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    update-module ${IMAGE_URL} failed: ${output}
    ${journal} =    Execute Command    journalctl -q --no-pager SYSLOG_IDENTIFIER=agent@${module_id}
    Should Not Contain    ${journal}    has failed    an update-module.d step failed
    ${image} =    Execute Command    runagent -m ${module_id} printenv IMAGE_URL
    ${image} =    Strip String    ${image}
    Should Be Equal    ${image}    ${IMAGE_URL}

Check service after install or update
    Read allocated web port
    Read admin credentials
    Wait until maubot is up

Check data kept by the update
    Skip If    r'${SCENARIO}' != 'update'    only the update scenario has data from the previous release
    ${plugins} =    Plugin list
    Should Contain    ${plugins}    "${PLUGIN_ID}"

Management UI is served through Traefik
    ${body}    ${status} =    Route    GET    /_matrix/maubot/
    Should Be Equal    ${status}    200
    Should Contain    ${body}    <title>Maubot Manager</title>

Wrong password is rejected
    ${body}    ${status} =    Login to maubot    not-the-password
    Should Be Equal    ${status}    401
    ${body}    ${status} =    Route    GET    /_matrix/maubot/v1/plugins
    Should Be Equal    ${status}    401

Plugin upload works
    Upload the test plugin
    ${plugins} =    Plugin list
    Should Contain    ${plugins}    "${PLUGIN_ID}"

Homeservers are written to the maubot configuration
    Configure current module    homeservers=${{[{"name": "example.org", "url": "https://matrix.example.org/", "secret": ""}]}}
    &{config} =    Get configuration
    Should Be Equal    ${config.homeservers}    ${{[{"name": "example.org", "url": "https://matrix.example.org", "secret": ""}]}}
    ${rendered} =    Execute Command    runagent -m ${module_id} cat config/maubot.yaml
    &{rendered} =    Evaluate    json.loads(r'''${rendered}''')    modules=json
    Should Be Equal    ${rendered.homeservers}    ${{{"example.org": {"url": "https://matrix.example.org", "secret": None}}}}
    Should Be Equal    ${rendered.server}[public_url]    https://${HOST}
    Wait until maubot is up

Reconfigure keeps password, sessions and plugins
    ${before_token} =    Set Variable    ${token}
    ${before_password} =    Set Variable    ${admin_password}
    Configure current module
    Read admin credentials
    Should Be Equal    ${admin_password}    ${before_password}
    Wait until maubot is up
    # The token secret is kept, so a session survives the restart
    Set Suite Variable    ${token}    ${before_token}
    ${plugins} =    Plugin list
    Should Contain    ${plugins}    "${PLUGIN_ID}"
    # A request without homeservers keeps them (clone, restore)
    &{config} =    Get configuration
    Length Should Be    ${config.homeservers}    1

Invalid homeservers are rejected
    ${output}    ${rc} =    Run action    configure-module    {"host": "${HOST}", "http2https": false, "lets_encrypt": false, "homeservers": [{"name": "example.org", "url": "matrix.example.org"}]}
    Should Not Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    invalid_homeserver_url
    ${output}    ${rc} =    Run action    configure-module    {"host": "${HOST}", "http2https": false, "lets_encrypt": false, "homeservers": [{"name": "bad name", "url": "https://a.test"}]}
    Should Not Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    invalid_server_name
    &{config} =    Get configuration
    Should Be Equal    ${config.homeservers}[0][name]    example.org

Admin password can be changed
    ${old} =    Set Variable    ${admin_password}
    Configure current module    admin_password=ci-new-password-${SCENARIO}
    Read admin credentials
    Should Be Equal    ${admin_password}    ci-new-password-${SCENARIO}
    Wait until maubot is up
    ${body}    ${status} =    Login to maubot    ${old}
    Should Be Equal    ${status}    401

Check private files
    ${modes} =    Execute Command    runagent -m ${module_id} stat -c '%a' maubot.json config config/maubot.yaml
    Should Be Equal    ${modes}    600\n700\n600
    ${environment} =    Execute Command    runagent -m ${module_id} cat environment
    Should Not Contain    ${environment}    ${admin_password}
    Should Not Contain    ${environment}    PASSWORD

Backup snapshot keeps maubot running
    ${output}    ${rc} =    Execute Command    runagent -m ${module_id} module-dump-state
    ...    return_rc=True    return_stderr=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot failed: ${output}
    ${db} =    Volume path    .backup-snapshot/maubot.db
    ${rc} =    Execute Command    runagent -m ${module_id} sh -c 'test -s ${db}'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot has no maubot.db
    # The snapshot container shares the volume with the running maubot; on
    # SELinux systems a wrong label would lock maubot out here.
    ${plugins} =    Plugin list
    Should Contain    ${plugins}    "${PLUGIN_ID}"
    ${upload} =    Execute Command    curl -sS --max-time 10 -o /dev/null -w '\%{http_code}' -H 'Authorization: Bearer ${token}' -H 'Content-Type: application/zip' --data-binary @/root/ci.mbp 'http://127.0.0.1:${web_port}/_matrix/maubot/v1/plugins/upload?allow_override=true'
    Should Match Regexp    ${upload}    ^20[01]$    maubot cannot write its volume after the snapshot
    ${rc} =    Execute Command    runagent -m ${module_id} module-cleanup-state
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot cleanup failed
    ${snapshot} =    Volume path    .backup-snapshot
    ${rc} =    Execute Command    runagent -m ${module_id} sh -c 'test ! -e ${snapshot}'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot remains after cleanup

Backup includes settings, plugins and the snapshot
    ${include} =    Execute Command    runagent -m ${module_id} sh -c 'cat ../etc/state-include.conf'
    FOR    ${line}    IN    state/maubot.json    volumes/maubot-data/plugins    volumes/maubot-data/.backup-snapshot
        Should Match Regexp    ${include}    (?m)^${line}$
    END

Module UI loads in cluster-admin
    [Tags]    ui
    Import Library    Browser
    New Browser    chromium    headless=True
    New Context    ignoreHTTPSErrors=True
    Login to cluster-admin
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}
    Wait For Elements State    iframe >>> h2 >> text="Status"    visible    timeout=20s
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/1._Status.png
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}?page=settings
    Wait For Elements State    iframe >>> h2 >> text="Settings"    visible    timeout=20s
    # The heading renders even when module tasks fail; the fields are only
    # enabled and filled after get-configuration has completed
    Wait For Elements State    iframe >>> input[placeholder="maubot.example.org"]    enabled    timeout=30s
    Get Property    iframe >>> input[placeholder="maubot.example.org"]    value    ==    ${HOST}
    Get Property    iframe >>> input#maubot-url    value    ==    https://${HOST}/_matrix/maubot/
    Get Property    iframe >>> input#maubot-admin-user    value    ==    admin
    Get Property    iframe >>> input#maubot-admin-password    type    ==    password
    Get Property    iframe >>> input#homeserver-name-0    value    ==    example.org
    Get Property    iframe >>> input#homeserver-url-0    value    ==    https://matrix.example.org
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/2._Settings.png
    Close Browser

Remove module
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

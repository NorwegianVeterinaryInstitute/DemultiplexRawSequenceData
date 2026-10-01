#!/usr/bin/bash

remove_nird_dir( )
{
    # delete /nird/home/georgmar/251110_M09180_0048_000000000-M7V7K or any other
    # directory under /nird/home/georgmar , passed as the first argument

    bw_binary="/usr/local/bin/bw"
    curl_binary="/usr/bin/curl"
    head_binary="/usr/bin/head"
    printf_binary="/usr/bin/printf"
    jq_binary="/usr/bin/jq"
    expect_binary="/usr/bin/expect"
    ssh_binary="/usr/bin/ssh"

    [[ ! -x "${printf_binary}" ]] && { echo "${printf_binary} is missing, exiting.\n";                    exit 2; }
    [[ ! -x "${bw_binary}" ]]     && { "${printf_binary}" "%s is missing, exiting.\n" "${bw_binary}";     exit 3; }
    [[ ! -x "${curl_binary}" ]]   && { "${printf_binary}" "%s is missing, exiting.\n" "${curl_binary}";   exit 4; }
    [[ ! -x "${head_binary}" ]]   && { "${printf_binary}" "%s is missing, exiting.\n" "${head_binary}";   exit 5; }
    [[ ! -x "${jq_binary}" ]]     && { "${printf_binary}" "%s is missing, exiting.\n" "${jq_binary}";     exit 6; }
    [[ ! -x "${expect_binary}" ]] && { "${printf_binary}" "%s is missing, exiting.\n" "${expect_binary}"; exit 7; }
    [[ ! -x "${ssh_binary}" ]]    && { "${printf_binary}" "%s is missing, exiting.\n" "${ssh_binary}";    exit 8; }


    port="8087"
    base_url="http://localhost:${port}"
    bw_vault_password_file="/home/gmarselis/src/bw/vault_password.txt"
    bw_vault_password=$( "${head_binary}" -n 1 "${bw_vault_password_file}" )
    bw_status="$( ${curl_binary} --no-progress-meter --request GET ${base_url}/status | ${jq_binary} --raw-output '.data.template.status' )"
    #nird_base_directory_absolute_path="/nird/datapeak/NS9305K/gmarselis/demux_transfer_test"
    nird_base_directory_absolute_path="/nird/datalake/NS9305K/test_demultiplex"
    nird_target_directory_relative_name="${1:-251110_M09180_0048_000000000-M7V7K}"

    [[ -z "${nird_target_directory_relative_name}" || "${nird_target_directory_relative_name}" =~ [[:space:]/] || "${nird_target_directory_relative_name}" == *".."* ]] && { ${printf_binary} "Invalid target directory\n"; exit 9; }


    nird_path_target="${nird_base_directory_absolute_path}/${nird_target_directory_relative_name}"
    nird_host="login.nird.sigma2.no"

    [[ -z "$bw_vault_password" ]] && { "${printf_binary}" "Could not get the value for \$bw_vault_password, exiting.\n";   exit 1; }

    if [[ ${bw_status} == "locked" ]]; then
        export BW_SESSION="$( ${curl_binary} --no-progress-meter --request POST --header "Content-Type: application/json" --data "{\"password\":\"$bw_vault_password\"}" ${base_url}/unlock | ${jq_binary} --raw-output '.data.raw' )"
    fi

    totp="$( ${curl_binary} --no-progress-meter ${base_url}/object/totp/${nird_host} | ${jq_binary} --raw-output '.data.data' )"
    password="$( ${curl_binary} --no-progress-meter ${base_url}/object/password/${nird_host} | ${jq_binary} --raw-output '.data.data' )"

    TOTP="${totp}" PASSWORD="${password}" TARGET="$( ${printf_binary} '%q' "${nird_path_target}" )" SSH="${ssh_binary}" HOST="${nird_host}" ${expect_binary} -c 'spawn $env(SSH) -tt -o PubkeyAuthentication=no -o PreferredAuthentications=keyboard-interactive -o IdentitiesOnly=yes -o IdentityAgent=none $env(HOST) -- /usr/bin/test -d $env(TARGET); after 2000; expect "One-time password"; send -- "$env(TOTP)\r"; expect "Password:"; send -- "$env(PASSWORD)\r"; set r [wait]; exit [lindex $r 3]' > /dev/null    # secrets and path reach Tcl through the environment, never parsed as Tcl or shown in ps
    test_directory_exists=$?

    if [[ ${test_directory_exists} -eq 0 ]]; then # if zero, directory exists

        TOTP="${totp}" PASSWORD="${password}" TARGET="$( ${printf_binary} '%q' "${nird_path_target}" )" SSH="${ssh_binary}" HOST="${nird_host}" ${expect_binary} -c 'spawn $env(SSH) -tt -o PubkeyAuthentication=no -o PreferredAuthentications=keyboard-interactive,password -o IdentitiesOnly=yes -o IdentityAgent=none $env(HOST) -- /usr/bin/rm -rf $env(TARGET); after 500; expect "One-time password"; send -- "$env(TOTP)\r"; expect "Password:"; send -- "$env(PASSWORD)\r"; set r [wait]; exit [lindex $r 3]' > /dev/null    # secrets and path reach Tcl through the environment, never parsed as Tcl or shown in ps
        rm_status=$?

        if [[ ${rm_status} -eq 0 ]]; then
            ${printf_binary} "%s:%s deleted.\n" ${nird_host} ${nird_path_target}
        else
            ${printf_binary} "Error removing %s:%s : exit status: %d\n" ${nird_host} ${nird_path_target} ${rm_status}
        fi
    elif [[ ${test_directory_exists} -eq 1 ]]; then # test -d exits 1 when the directory is missing; ssh exits 255 on a login or connection failure
        ${printf_binary} "Directory ${nird_host}:${nird_path_target} does not exist, exiting.\n"
    else
        ${printf_binary} "Could not check %s:%s: exit status %d (login, 2FA or connection failure), exiting.\n" "${nird_host}" "${nird_path_target}" "${test_directory_exists}"
        exit 10
    fi

    unset totp
    unset password
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    remove_nird_dir $@
fi


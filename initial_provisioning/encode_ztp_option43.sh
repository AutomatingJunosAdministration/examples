#!/bin/sh

#################################################################
# Script to prompt for various parameters used in Junos
# Zero Touch Provisioning (ZTP) and encode those paramters
# into a string of hexadecimal digits that can be configured
# as the dhcp-attributes on a Junos device's DHCP server.
#################################################################

function option43_tlv {
    suboption=`printf '%02x' "$1"`
    string="$2"
    length=`echo -n "$string" | wc -c`
    if [ "$length" -gt 255 ]; then
        echo "Length of string exceeds 255 characters. Length: $length String: $string" >&2
        exit 1
    fi
    hex_length=`printf '%02x' "$length"`
    hex_string=`echo -n "$string" | xxd -c 256 -p`
    echo -n "$suboption$hex_length$hex_string"
}

while true; do
    read -p 'Protocol (sub-option 03): ' protocol
    if [ "$protocol" = 'tftp' ] || [ "$protocol" = 'ftp' ] || [ "$protocol" = 'http' ]; then
        break
    else
        echo 'Invalid protocol. Only tftp, ftp, and http are valid.' >&2
    fi
done
read -p 'Path and filename of Junos image (sub-option 00): ' image_file
if [ -z $image_file ]; then
    read -p 'Path and filename of Junos image (alternate sub-option 04): ' alt_image_file
fi
read -p 'Path and filename of Junos configuration (sub-option 01): ' config_file

hex_string=''
if [ -n "$image_file" ]; then
    hex_string=$hex_string`option43_tlv 0 $image_file`
fi
if [ -n "$config_file" ]; then
    hex_string=$hex_string`option43_tlv 1 $config_file`
fi
if [ -n "$protocol" ]; then
    hex_string=$hex_string`option43_tlv 3 $protocol`
fi
if [ -n "$alt_image_file" ]; then
    hex_string=$hex_string`option43_tlv 4 $alt_image_file`
fi
echo "Hex string is: $hex_string" 

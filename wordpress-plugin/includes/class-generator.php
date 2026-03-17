<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class Consent_Txt_Generator {

    public static function generate() {
        $s = Consent_Txt_Settings::get();

        if ( ! empty( $s['use_custom_json'] ) && ! empty( $s['custom_json'] ) ) {
            $custom = json_decode( $s['custom_json'], true );
            if ( json_last_error() === JSON_ERROR_NONE ) return $custom;
        }

        $manifest = array( 'version' => CONSENT_TXT_SPEC_VERSION );

        // Publisher.
        $publisher = array(
            'name'    => $s['publisher_name'] ?: get_bloginfo( 'name' ),
            'url'     => $s['publisher_url'] ?: home_url(),
            'contact' => $s['publisher_contact'] ?: 'mailto:' . get_option( 'admin_email' ),
        );
        if ( ! empty( $s['jurisdictions'] ) ) {
            $publisher['jurisdictions'] = array_map( 'trim', explode( ',', $s['jurisdictions'] ) );
        }
        if ( ! empty( $s['terms_url'] ) ) {
            $publisher['terms_url'] = $s['terms_url'];
        }
        $manifest['publisher'] = $publisher;

        // Defaults.
        $defaults = array();
        $defaults['fallbacks'] = array(
            'unexpressible_state' => $s['fallback_unexpressible'] ?: 'deny',
            'unknown_identity'    => $s['fallback_unknown_id'] ?: 'deny',
        );
        if ( ! empty( $s['standard'] ) ) {
            $defaults['standard'] = self::build_policies( $s['standard'] );
        }
        if ( ! empty( $s['experimental'] ) ) {
            $defaults['experimental'] = self::build_policies( $s['experimental'] );
        }
        $manifest['defaults'] = $defaults;

        // Rules.
        if ( ! empty( $s['rules'] ) ) {
            $rules = array();
            foreach ( $s['rules'] as $r ) {
                if ( empty( $r['path'] ) ) continue;
                $rule = array( 'match' => array( 'path' => $r['path'] ) );
                if ( ! empty( $r['standard'] ) ) {
                    $rule['standard'] = self::build_policies( $r['standard'] );
                }
                if ( ! empty( $r['experimental'] ) ) {
                    $rule['experimental'] = self::build_policies( $r['experimental'] );
                }
                $rules[] = $rule;
            }
            if ( $rules ) $manifest['rules'] = $rules;
        }

        // Endpoints.
        $endpoints = array();
        foreach ( array( 'payment', 'receipts', 'verification', 'tdm_policy' ) as $key ) {
            $val = $s[ 'endpoint_' . $key ] ?? '';
            if ( $val ) $endpoints[ $key ] = $val;
        }
        if ( $endpoints ) $manifest['endpoints'] = $endpoints;

        // Interop.
        if ( ! empty( $s['emit'] ) ) {
            $manifest['interop'] = array( 'emit' => array_values( $s['emit'] ) );
        }

        return $manifest;
    }

    public static function to_json() {
        return wp_json_encode( self::generate(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
    }

    private static function build_policies( $policies ) {
        $result = array();
        foreach ( $policies as $cat => $val ) {
            if ( empty( $val['state'] ) ) continue;
            $entry = array( 'state' => $val['state'] );
            if ( ! empty( $val['conditions'] ) ) {
                $entry['conditions'] = $val['conditions'];
            }
            $result[ $cat ] = $entry;
        }
        return $result;
    }
}

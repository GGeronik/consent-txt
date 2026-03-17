<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class Consent_Txt_Settings {

    const STANDARD_CATEGORIES = array(
        'train-ai'  => 'AI Model Training',
        'search'    => 'Search Indexing',
        'ai-input'  => 'AI Inference / RAG',
    );

    const EXPERIMENTAL_CATEGORIES = array(
        'agentic-access' => 'AI Agent Browsing',
        'transform'      => 'Summarization / Synthesis',
        'generate-media' => 'Media Generation',
        'embedding'      => 'Vector Embeddings',
    );

    const STATES = array(
        'allow'       => 'Allow',
        'deny'        => 'Deny',
        'conditional' => 'Conditional',
        'charge'      => 'Charge',
        'unknown'     => 'Unknown',
    );

    const CONDITION_KEYS = array(
        'identity', 'citation_required', 'link_required', 'attribution_required',
        'max_excerpt_chars', 'max_tokens', 'verbatim_allowed',
        'freshness_delay_seconds', 'rate_limit_per_day', 'payment_plan',
    );

    public static function defaults() {
        return array(
            'enabled'           => true,
            'publisher_name'    => get_bloginfo( 'name' ),
            'publisher_url'     => home_url(),
            'publisher_contact' => 'mailto:' . get_option( 'admin_email' ),
            'jurisdictions'     => '',
            'terms_url'         => '',
            'fallback_unexpressible' => 'deny',
            'fallback_unknown_id'    => 'deny',
            'standard'          => array(
                'train-ai'  => array( 'state' => 'deny' ),
                'search'    => array( 'state' => 'allow' ),
                'ai-input'  => array( 'state' => 'deny' ),
            ),
            'experimental'      => array(),
            'rules'             => array(),
            'endpoint_payment'      => '',
            'endpoint_receipts'     => '',
            'endpoint_verification' => '',
            'endpoint_tdm_policy'   => '',
            'emit'              => array( 'robots-txt', 'aipref-header' ),
            'custom_json'       => '',
            'use_custom_json'   => false,
        );
    }

    public static function get() {
        return wp_parse_args( get_option( CONSENT_TXT_OPTION_KEY, array() ), self::defaults() );
    }

    public function handle_save() {
        if ( ! isset( $_POST['consent_txt_save'] ) ) return;
        check_admin_referer( 'consent_txt_settings', 'consent_txt_nonce' );
        if ( ! current_user_can( 'manage_options' ) ) return;

        $settings = array(
            'enabled'           => ! empty( $_POST['enabled'] ),
            'publisher_name'    => sanitize_text_field( wp_unslash( $_POST['publisher_name'] ?? '' ) ),
            'publisher_url'     => esc_url_raw( wp_unslash( $_POST['publisher_url'] ?? '' ) ),
            'publisher_contact' => sanitize_text_field( wp_unslash( $_POST['publisher_contact'] ?? '' ) ),
            'jurisdictions'     => sanitize_text_field( wp_unslash( $_POST['jurisdictions'] ?? '' ) ),
            'terms_url'         => esc_url_raw( wp_unslash( $_POST['terms_url'] ?? '' ) ),
            'fallback_unexpressible' => in_array( $_POST['fallback_unexpressible'] ?? '', array('allow','deny','unknown'), true ) ? $_POST['fallback_unexpressible'] : 'deny',
            'fallback_unknown_id'    => in_array( $_POST['fallback_unknown_id'] ?? '', array('allow','deny','unknown'), true ) ? $_POST['fallback_unknown_id'] : 'deny',
            'standard'          => $this->sanitize_policies( $_POST['standard'] ?? array() ),
            'experimental'      => $this->sanitize_policies( $_POST['experimental'] ?? array() ),
            'rules'             => $this->sanitize_rules( $_POST['rules'] ?? array() ),
            'endpoint_payment'      => esc_url_raw( wp_unslash( $_POST['endpoint_payment'] ?? '' ) ),
            'endpoint_receipts'     => esc_url_raw( wp_unslash( $_POST['endpoint_receipts'] ?? '' ) ),
            'endpoint_verification' => esc_url_raw( wp_unslash( $_POST['endpoint_verification'] ?? '' ) ),
            'endpoint_tdm_policy'   => esc_url_raw( wp_unslash( $_POST['endpoint_tdm_policy'] ?? '' ) ),
            'emit'              => $this->sanitize_emit( $_POST['emit'] ?? array() ),
            'custom_json'       => wp_unslash( $_POST['custom_json'] ?? '' ),
            'use_custom_json'   => ! empty( $_POST['use_custom_json'] ),
        );

        update_option( CONSENT_TXT_OPTION_KEY, $settings );
        flush_rewrite_rules();
        add_settings_error( 'consent_txt', 'saved', __( 'Manifest saved and live.', 'consent-txt' ), 'success' );
    }

    private function sanitize_policies( $input ) {
        if ( ! is_array( $input ) ) return array();
        $clean = array();
        $valid_states = array_keys( self::STATES );
        foreach ( $input as $cat => $val ) {
            if ( ! is_array( $val ) || empty( $val['state'] ) ) continue;
            if ( ! in_array( $val['state'], $valid_states, true ) ) continue;
            $entry = array( 'state' => $val['state'] );
            if ( ! empty( $val['conditions'] ) && is_array( $val['conditions'] ) ) {
                $conds = array();
                foreach ( $val['conditions'] as $k => $v ) {
                    if ( $v === '' || $v === null ) continue;
                    if ( in_array( $k, array( 'citation_required', 'link_required', 'attribution_required', 'verbatim_allowed' ), true ) ) {
                        $conds[ $k ] = (bool) $v;
                    } elseif ( in_array( $k, array( 'max_excerpt_chars', 'max_tokens', 'freshness_delay_seconds', 'rate_limit_per_day' ), true ) ) {
                        $conds[ $k ] = absint( $v );
                    } elseif ( $k === 'identity' && in_array( $v, array( 'none', 'verified', 'signed' ), true ) ) {
                        $conds[ $k ] = $v;
                    } elseif ( $k === 'payment_plan' ) {
                        $conds[ $k ] = sanitize_text_field( $v );
                    }
                }
                if ( $conds ) $entry['conditions'] = $conds;
            }
            $clean[ sanitize_text_field( $cat ) ] = $entry;
        }
        return $clean;
    }

    private function sanitize_rules( $input ) {
        if ( ! is_array( $input ) ) return array();
        $clean = array();
        foreach ( $input as $rule ) {
            if ( empty( $rule['path'] ) ) continue;
            $entry = array(
                'path'     => sanitize_text_field( $rule['path'] ),
                'standard' => $this->sanitize_policies( $rule['standard'] ?? array() ),
            );
            if ( ! empty( $rule['experimental'] ) ) {
                $entry['experimental'] = $this->sanitize_policies( $rule['experimental'] ?? array() );
            }
            $clean[] = $entry;
        }
        return $clean;
    }

    private function sanitize_emit( $input ) {
        if ( ! is_array( $input ) ) return array();
        $valid = array( 'robots-txt', 'aipref-header', 'aipref-robots', 'x-robots-tag', 'google-extended', 'tdmrep' );
        return array_values( array_intersect( $input, $valid ) );
    }
}

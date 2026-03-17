<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class Consent_Txt_Server {

    private static $instance = null;

    public static function instance() {
        if ( null === self::$instance ) self::$instance = new self();
        return self::$instance;
    }

    private function __construct() {
        add_action( 'template_redirect', array( $this, 'maybe_serve' ) );
        add_action( 'parse_request', array( $this, 'fallback_serve' ) );
    }

    public function maybe_serve() {
        if ( ! get_query_var( 'consent_txt_serve' ) ) return;
        $this->serve();
    }

    public function fallback_serve( $wp ) {
        $path = wp_parse_url( $_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH );
        if ( $path === '/.well-known/consent-manifest.json' || $path === '/.well-known/consent.txt' ) {
            $this->serve();
        }
    }

    private function serve() {
        $s = Consent_Txt_Settings::get();
        if ( empty( $s['enabled'] ) ) {
            status_header( 404 );
            header( 'Content-Type: application/json' );
            echo '{"error":"consent manifest not enabled"}';
            exit;
        }

        $json = Consent_Txt_Generator::to_json();

        status_header( 200 );
        header( 'Content-Type: application/json; charset=utf-8' );
        header( 'Cache-Control: public, max-age=86400' );
        header( 'Access-Control-Allow-Origin: *' );
        header( 'X-Consent-Manifest-Version: ' . CONSENT_TXT_SPEC_VERSION );
        echo $json;
        exit;
    }
}

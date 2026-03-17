<?php
/**
 * Plugin Name:       consent.txt
 * Plugin URI:        https://github.com/GGeronik/consent.txt
 * Description:       The control plane for AI content access. Author one manifest, compile into robots.txt, AIPREF headers, X-Robots-Tag, and more.
 * Version:           0.1.0
 * Requires at least: 5.8
 * Requires PHP:      7.4
 * Author:            George Geronikolas
 * Author URI:        https://github.com/GGeronik
 * License:           Apache-2.0
 * License URI:       https://www.apache.org/licenses/LICENSE-2.0
 * Text Domain:       consent-txt
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'CONSENT_TXT_VERSION', '0.1.0' );
define( 'CONSENT_TXT_SPEC_VERSION', '0.1' );
define( 'CONSENT_TXT_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'CONSENT_TXT_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'CONSENT_TXT_OPTION_KEY', 'consent_txt_manifest' );

require_once CONSENT_TXT_PLUGIN_DIR . 'includes/class-settings.php';
require_once CONSENT_TXT_PLUGIN_DIR . 'includes/class-generator.php';
require_once CONSENT_TXT_PLUGIN_DIR . 'includes/class-compiler.php';
require_once CONSENT_TXT_PLUGIN_DIR . 'includes/class-server.php';
require_once CONSENT_TXT_PLUGIN_DIR . 'includes/presets.php';

final class Consent_Txt {

    private static $instance = null;

    public static function instance() {
        if ( null === self::$instance ) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct() {
        add_action( 'init', array( $this, 'register_rewrites' ) );
        add_action( 'admin_menu', array( $this, 'admin_menu' ) );
        add_action( 'admin_enqueue_scripts', array( $this, 'admin_assets' ) );
        add_filter( 'plugin_action_links_' . plugin_basename( __FILE__ ), array( $this, 'action_links' ) );

        // Inject compiled AIPREF and X-Robots-Tag headers into responses.
        add_action( 'send_headers', array( $this, 'inject_headers' ) );

        Consent_Txt_Server::instance();
    }

    public function register_rewrites() {
        add_rewrite_rule( '\.well-known/consent-manifest\.json$', 'index.php?consent_txt_serve=1', 'top' );
        add_rewrite_rule( '\.well-known/consent\.txt$', 'index.php?consent_txt_serve=1', 'top' );
        add_rewrite_tag( '%consent_txt_serve%', '1' );
    }

    public function admin_menu() {
        add_options_page(
            __( 'consent.txt', 'consent-txt' ),
            __( 'consent.txt', 'consent-txt' ),
            'manage_options',
            'consent-txt',
            array( $this, 'render_admin' )
        );
    }

    public function admin_assets( $hook ) {
        if ( 'settings_page_consent-txt' !== $hook ) return;

        wp_enqueue_style( 'consent-txt-admin', CONSENT_TXT_PLUGIN_URL . 'assets/css/admin.css', array(), CONSENT_TXT_VERSION );
        wp_enqueue_script( 'consent-txt-admin', CONSENT_TXT_PLUGIN_URL . 'assets/js/admin.js', array( 'jquery' ), CONSENT_TXT_VERSION, true );

        wp_localize_script( 'consent-txt-admin', 'consentTxt', array(
            'nonce'    => wp_create_nonce( 'consent_txt_nonce' ),
            'presets'  => consent_txt_get_presets(),
            'siteName' => get_bloginfo( 'name' ),
            'siteUrl'  => home_url(),
            'email'    => get_option( 'admin_email' ),
        ) );
    }

    public function render_admin() {
        if ( ! current_user_can( 'manage_options' ) ) return;
        $settings = new Consent_Txt_Settings();
        $settings->handle_save();
        include CONSENT_TXT_PLUGIN_DIR . 'templates/admin-page.php';
    }

    public function action_links( $links ) {
        array_unshift( $links, sprintf(
            '<a href="%s">%s</a>',
            admin_url( 'options-general.php?page=consent-txt' ),
            __( 'Settings', 'consent-txt' )
        ) );
        return $links;
    }

    /**
     * Inject compiled HTTP headers into frontend responses.
     */
    public function inject_headers() {
        if ( is_admin() || wp_doing_ajax() || wp_doing_cron() ) return;

        $s = Consent_Txt_Settings::get();
        if ( empty( $s['enabled'] ) ) return;

        $manifest = Consent_Txt_Generator::generate();
        $emit = $manifest['interop']['emit'] ?? array();

        if ( in_array( 'aipref-header', $emit, true ) ) {
            $header = Consent_Txt_Compiler::aipref_header( $manifest );
            if ( $header ) {
                header( $header );
            }
        }

        if ( in_array( 'x-robots-tag', $emit, true ) ) {
            $tags = Consent_Txt_Compiler::x_robots_tag( $manifest );
            foreach ( explode( "\n", $tags ) as $tag ) {
                $tag = trim( $tag );
                if ( $tag ) header( $tag );
            }
        }

        if ( in_array( 'tdmrep', $emit, true ) ) {
            $tdm = Consent_Txt_Compiler::tdmrep_header( $manifest );
            if ( $tdm ) header( $tdm );
        }
    }

    public static function activate() {
        $p = self::instance();
        $p->register_rewrites();
        flush_rewrite_rules();

        if ( false === get_option( CONSENT_TXT_OPTION_KEY ) ) {
            update_option( CONSENT_TXT_OPTION_KEY, Consent_Txt_Settings::defaults() );
        }
    }

    public static function deactivate() {
        flush_rewrite_rules();
    }
}

register_activation_hook( __FILE__, array( 'Consent_Txt', 'activate' ) );
register_deactivation_hook( __FILE__, array( 'Consent_Txt', 'deactivate' ) );
Consent_Txt::instance();

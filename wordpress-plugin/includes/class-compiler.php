<?php
if ( ! defined( 'ABSPATH' ) ) exit;

/**
 * PHP port of the consent.txt compiler for runtime header injection.
 * Handles lowering rich authoring states to wire-format values.
 */
class Consent_Txt_Compiler {

    /**
     * Lower a rich state to allow/deny for wire formats.
     */
    private static function lower( $state, $manifest ) {
        if ( in_array( $state, array( 'allow', 'deny' ), true ) ) return $state;
        if ( $state === 'unknown' ) return null;
        $fb = $manifest['defaults']['fallbacks']['unexpressible_state'] ?? 'deny';
        return $fb;
    }

    private static function get_state( $policies, $category ) {
        return $policies[ $category ]['state'] ?? 'unknown';
    }

    /**
     * Compile AIPREF Content-Usage header value.
     */
    public static function aipref_header( $manifest ) {
        $std = $manifest['defaults']['standard'] ?? array();
        $parts = array();
        foreach ( array( 'train-ai', 'search', 'ai-input' ) as $cat ) {
            $state = self::get_state( $std, $cat );
            $lowered = self::lower( $state, $manifest );
            if ( $lowered === 'allow' ) $parts[] = "{$cat}=y";
            elseif ( $lowered === 'deny' ) $parts[] = "{$cat}=n";
        }
        return $parts ? 'Content-Usage: ' . implode( ', ', $parts ) : '';
    }

    /**
     * Compile X-Robots-Tag header values.
     */
    public static function x_robots_tag( $manifest ) {
        $std = $manifest['defaults']['standard'] ?? array();
        $tags = array();

        $search = self::lower( self::get_state( $std, 'search' ), $manifest );
        if ( $search === 'deny' ) {
            return 'X-Robots-Tag: noindex, nofollow';
        }

        $ai_input = $std['ai-input'] ?? array();
        $max_chars = $ai_input['conditions']['max_excerpt_chars'] ?? null;
        if ( is_int( $max_chars ) ) {
            $tags[] = "X-Robots-Tag: max-snippet:{$max_chars}";
        }

        $train = self::lower( self::get_state( $std, 'train-ai' ), $manifest );
        if ( $train === 'deny' ) {
            $tags[] = 'X-Robots-Tag: googlebot: noai, noimageai';
        }

        return implode( "\n", $tags );
    }

    /**
     * Compile TDMRep Link header.
     */
    public static function tdmrep_header( $manifest ) {
        $url = $manifest['endpoints']['tdm_policy'] ?? '';
        if ( ! $url ) return '';
        return "Link: <{$url}>; rel=\"tdm-policy\"";
    }
}

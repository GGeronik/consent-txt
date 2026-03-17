<?php
if ( ! defined( 'ABSPATH' ) ) exit;

function consent_txt_get_presets() {
    return array(
        'minimal' => array(
            'label'       => 'Minimal Protection',
            'description' => 'Block AI training, allow search indexing.',
            'settings'    => array(
                'standard' => array(
                    'train-ai'  => array( 'state' => 'deny' ),
                    'search'    => array( 'state' => 'allow' ),
                    'ai-input'  => array( 'state' => 'deny' ),
                ),
                'experimental' => array(),
                'emit' => array( 'robots-txt', 'aipref-header' ),
            ),
        ),
        'news' => array(
            'label'       => 'News Publisher',
            'description' => 'Block training, allow search, conditional inference with attribution.',
            'settings'    => array(
                'standard' => array(
                    'train-ai'  => array( 'state' => 'deny' ),
                    'search'    => array( 'state' => 'allow' ),
                    'ai-input'  => array(
                        'state'      => 'conditional',
                        'conditions' => array(
                            'identity'          => 'signed',
                            'citation_required' => true,
                            'link_required'     => true,
                            'max_excerpt_chars' => 160,
                            'max_tokens'        => 500,
                        ),
                    ),
                ),
                'experimental' => array(
                    'transform'      => array( 'state' => 'deny' ),
                    'generate-media' => array( 'state' => 'deny' ),
                ),
                'emit' => array( 'robots-txt', 'aipref-header', 'x-robots-tag', 'google-extended', 'tdmrep' ),
            ),
        ),
        'saas' => array(
            'label'       => 'SaaS / Documentation',
            'description' => 'Block training by default, allow inference for documentation paths.',
            'settings'    => array(
                'standard' => array(
                    'train-ai'  => array( 'state' => 'deny' ),
                    'search'    => array( 'state' => 'allow' ),
                    'ai-input'  => array(
                        'state'      => 'conditional',
                        'conditions' => array(
                            'attribution_required' => true,
                            'link_required'        => true,
                        ),
                    ),
                ),
                'experimental' => array(),
                'emit' => array( 'robots-txt', 'aipref-header' ),
            ),
        ),
        'open' => array(
            'label'       => 'Open / Permissive',
            'description' => 'Allow most AI uses with attribution. For open-source and academic sites.',
            'settings'    => array(
                'standard' => array(
                    'train-ai'  => array(
                        'state'      => 'conditional',
                        'conditions' => array( 'attribution_required' => true ),
                    ),
                    'search'    => array( 'state' => 'allow' ),
                    'ai-input'  => array( 'state' => 'allow' ),
                ),
                'experimental' => array(
                    'embedding'       => array( 'state' => 'allow' ),
                    'agentic-access'  => array( 'state' => 'allow' ),
                    'transform'       => array(
                        'state'      => 'conditional',
                        'conditions' => array( 'attribution_required' => true ),
                    ),
                ),
                'emit' => array( 'robots-txt', 'aipref-header' ),
            ),
        ),
        'lockdown' => array(
            'label'       => 'Total Lockdown',
            'description' => 'Block all AI access. Only allow traditional search indexing.',
            'settings'    => array(
                'standard' => array(
                    'train-ai'  => array( 'state' => 'deny' ),
                    'search'    => array( 'state' => 'allow' ),
                    'ai-input'  => array( 'state' => 'deny' ),
                ),
                'experimental' => array(
                    'agentic-access' => array( 'state' => 'deny' ),
                    'transform'      => array( 'state' => 'deny' ),
                    'generate-media' => array( 'state' => 'deny' ),
                    'embedding'      => array( 'state' => 'deny' ),
                ),
                'emit' => array( 'robots-txt', 'aipref-header', 'aipref-robots', 'x-robots-tag', 'google-extended' ),
            ),
        ),
    );
}

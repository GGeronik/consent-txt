<?php
if ( ! defined( 'ABSPATH' ) ) exit;
$s       = Consent_Txt_Settings::get();
$preview = Consent_Txt_Generator::to_json();
$live_url = home_url( '/.well-known/consent-manifest.json' );
$state_options = Consent_Txt_Settings::STATES;
?>
<div class="wrap ctxt-wrap">
    <h1><span class="ctxt-logo">consent.txt</span> <span class="ctxt-sub">Consent Manifest v0.1</span></h1>

    <?php settings_errors( 'consent_txt' ); ?>

    <?php if ( ! empty( $s['enabled'] ) ) : ?>
    <div class="ctxt-bar ctxt-bar--on">&#9679; Live at <a href="<?php echo esc_url( $live_url ); ?>" target="_blank"><code><?php echo esc_html( $live_url ); ?></code></a></div>
    <?php else : ?>
    <div class="ctxt-bar ctxt-bar--off">&#9679; Inactive — enable below to start serving.</div>
    <?php endif; ?>

    <form method="post" id="ctxt-form">
        <?php wp_nonce_field( 'consent_txt_settings', 'consent_txt_nonce' ); ?>

        <div class="ctxt-grid">
            <div class="ctxt-main">

                <!-- Presets -->
                <div class="ctxt-card">
                    <h2>Quick Start</h2>
                    <div class="ctxt-presets" id="ctxt-presets">
                        <?php foreach ( consent_txt_get_presets() as $key => $p ) : ?>
                        <button type="button" class="ctxt-preset" data-preset="<?php echo esc_attr( $key ); ?>">
                            <strong><?php echo esc_html( $p['label'] ); ?></strong>
                            <span><?php echo esc_html( $p['description'] ); ?></span>
                        </button>
                        <?php endforeach; ?>
                    </div>
                </div>

                <!-- Enable -->
                <div class="ctxt-card">
                    <label class="ctxt-toggle">
                        <input type="checkbox" name="enabled" value="1" <?php checked( $s['enabled'] ); ?> />
                        <span class="ctxt-toggle-track"></span>
                        Serve consent manifest
                    </label>
                </div>

                <!-- Publisher -->
                <div class="ctxt-card">
                    <h2>Publisher</h2>
                    <table class="form-table">
                        <tr><th><label for="publisher_name">Name</label></th>
                            <td><input type="text" name="publisher_name" id="publisher_name" value="<?php echo esc_attr( $s['publisher_name'] ); ?>" class="regular-text" /></td></tr>
                        <tr><th><label for="publisher_url">URL</label></th>
                            <td><input type="url" name="publisher_url" id="publisher_url" value="<?php echo esc_attr( $s['publisher_url'] ); ?>" class="regular-text" /></td></tr>
                        <tr><th><label for="publisher_contact">Contact</label></th>
                            <td><input type="text" name="publisher_contact" id="publisher_contact" value="<?php echo esc_attr( $s['publisher_contact'] ); ?>" class="regular-text" placeholder="mailto:ai@example.com" /></td></tr>
                        <tr><th><label for="jurisdictions">Jurisdictions</label></th>
                            <td><input type="text" name="jurisdictions" id="jurisdictions" value="<?php echo esc_attr( $s['jurisdictions'] ); ?>" class="regular-text" placeholder="US, EU, GB" /></td></tr>
                        <tr><th><label for="terms_url">Terms URL</label></th>
                            <td><input type="url" name="terms_url" id="terms_url" value="<?php echo esc_attr( $s['terms_url'] ); ?>" class="regular-text" /></td></tr>
                    </table>
                </div>

                <!-- Fallbacks -->
                <div class="ctxt-card">
                    <h2>Fallback Behavior</h2>
                    <p class="description">When the manifest uses <code>charge</code> or <code>conditional</code> but the target surface only supports allow/deny, how should the compiler lower it?</p>
                    <table class="form-table">
                        <tr><th>Unexpressible states</th>
                            <td><select name="fallback_unexpressible">
                                <?php foreach ( array('deny','allow','unknown') as $v ) : ?>
                                <option value="<?php echo esc_attr($v); ?>" <?php selected($s['fallback_unexpressible'], $v); ?>><?php echo esc_html($v); ?></option>
                                <?php endforeach; ?>
                            </select></td></tr>
                        <tr><th>Unknown identity</th>
                            <td><select name="fallback_unknown_id">
                                <?php foreach ( array('deny','allow','unknown') as $v ) : ?>
                                <option value="<?php echo esc_attr($v); ?>" <?php selected($s['fallback_unknown_id'], $v); ?>><?php echo esc_html($v); ?></option>
                                <?php endforeach; ?>
                            </select></td></tr>
                    </table>
                </div>

                <!-- Standard Policies -->
                <div class="ctxt-card">
                    <h2>Standard Categories</h2>
                    <p class="description">These map to recognized public standards (AIPREF, Google-Extended, robots.txt).</p>
                    <?php foreach ( Consent_Txt_Settings::STANDARD_CATEGORIES as $cat => $label ) :
                        $current = $s['standard'][ $cat ] ?? array( 'state' => 'unknown' );
                    ?>
                    <div class="ctxt-policy-row">
                        <div class="ctxt-policy-label"><strong><?php echo esc_html( $label ); ?></strong> <code><?php echo esc_html( $cat ); ?></code></div>
                        <div class="ctxt-policy-state">
                            <select name="standard[<?php echo esc_attr( $cat ); ?>][state]" class="ctxt-state-select" data-target="std-cond-<?php echo esc_attr( $cat ); ?>">
                                <?php foreach ( $state_options as $sv => $sl ) : ?>
                                <option value="<?php echo esc_attr($sv); ?>" <?php selected( $current['state'] ?? 'unknown', $sv ); ?>><?php echo esc_html($sl); ?></option>
                                <?php endforeach; ?>
                            </select>
                        </div>
                        <div class="ctxt-cond-panel" id="std-cond-<?php echo esc_attr( $cat ); ?>" style="<?php echo in_array($current['state'] ?? '', array('conditional','charge')) ? '' : 'display:none;'; ?>">
                            <?php $cond = $current['conditions'] ?? array(); ?>
                            <label><input type="checkbox" name="standard[<?php echo esc_attr($cat); ?>][conditions][citation_required]" value="1" <?php checked( ! empty( $cond['citation_required'] ) ); ?> /> Citation required</label>
                            <label><input type="checkbox" name="standard[<?php echo esc_attr($cat); ?>][conditions][link_required]" value="1" <?php checked( ! empty( $cond['link_required'] ) ); ?> /> Link-back required</label>
                            <label><input type="checkbox" name="standard[<?php echo esc_attr($cat); ?>][conditions][attribution_required]" value="1" <?php checked( ! empty( $cond['attribution_required'] ) ); ?> /> Attribution required</label>
                            <label>Identity: <select name="standard[<?php echo esc_attr($cat); ?>][conditions][identity]">
                                <option value="">—</option>
                                <?php foreach ( array('none','verified','signed') as $id ) : ?>
                                <option value="<?php echo $id; ?>" <?php selected( $cond['identity'] ?? '', $id ); ?>><?php echo $id; ?></option>
                                <?php endforeach; ?>
                            </select></label>
                            <label>Max excerpt chars: <input type="number" name="standard[<?php echo esc_attr($cat); ?>][conditions][max_excerpt_chars]" value="<?php echo esc_attr( $cond['max_excerpt_chars'] ?? '' ); ?>" class="small-text" /></label>
                            <label>Max tokens: <input type="number" name="standard[<?php echo esc_attr($cat); ?>][conditions][max_tokens]" value="<?php echo esc_attr( $cond['max_tokens'] ?? '' ); ?>" class="small-text" /></label>
                            <label>Rate limit/day: <input type="number" name="standard[<?php echo esc_attr($cat); ?>][conditions][rate_limit_per_day]" value="<?php echo esc_attr( $cond['rate_limit_per_day'] ?? '' ); ?>" class="small-text" /></label>
                            <label>Payment plan: <input type="text" name="standard[<?php echo esc_attr($cat); ?>][conditions][payment_plan]" value="<?php echo esc_attr( $cond['payment_plan'] ?? '' ); ?>" class="regular-text" placeholder="e.g. premium-rag" /></label>
                        </div>
                    </div>
                    <?php endforeach; ?>
                </div>

                <!-- Experimental Policies -->
                <div class="ctxt-card">
                    <h2>Experimental Categories <span class="ctxt-badge">Optional</span></h2>
                    <p class="description">Higher-resolution controls for enforcement runtimes. Not emitted into standards-track surfaces.</p>
                    <?php foreach ( Consent_Txt_Settings::EXPERIMENTAL_CATEGORIES as $cat => $label ) :
                        $current = $s['experimental'][ $cat ] ?? array( 'state' => 'unknown' );
                    ?>
                    <div class="ctxt-policy-row">
                        <div class="ctxt-policy-label"><strong><?php echo esc_html( $label ); ?></strong> <code><?php echo esc_html( $cat ); ?></code></div>
                        <div class="ctxt-policy-state">
                            <select name="experimental[<?php echo esc_attr( $cat ); ?>][state]" class="ctxt-state-select" data-target="exp-cond-<?php echo esc_attr( $cat ); ?>">
                                <?php foreach ( $state_options as $sv => $sl ) : ?>
                                <option value="<?php echo esc_attr($sv); ?>" <?php selected( $current['state'] ?? 'unknown', $sv ); ?>><?php echo esc_html($sl); ?></option>
                                <?php endforeach; ?>
                            </select>
                        </div>
                        <div class="ctxt-cond-panel" id="exp-cond-<?php echo esc_attr( $cat ); ?>" style="<?php echo in_array($current['state'] ?? '', array('conditional','charge')) ? '' : 'display:none;'; ?>">
                            <?php $cond = $current['conditions'] ?? array(); ?>
                            <label><input type="checkbox" name="experimental[<?php echo esc_attr($cat); ?>][conditions][citation_required]" value="1" <?php checked( ! empty( $cond['citation_required'] ) ); ?> /> Citation</label>
                            <label><input type="checkbox" name="experimental[<?php echo esc_attr($cat); ?>][conditions][attribution_required]" value="1" <?php checked( ! empty( $cond['attribution_required'] ) ); ?> /> Attribution</label>
                            <label>Identity: <select name="experimental[<?php echo esc_attr($cat); ?>][conditions][identity]">
                                <option value="">—</option>
                                <?php foreach ( array('none','verified','signed') as $id ) : ?>
                                <option value="<?php echo $id; ?>" <?php selected( $cond['identity'] ?? '', $id ); ?>><?php echo $id; ?></option>
                                <?php endforeach; ?>
                            </select></label>
                            <label>Rate limit/day: <input type="number" name="experimental[<?php echo esc_attr($cat); ?>][conditions][rate_limit_per_day]" value="<?php echo esc_attr( $cond['rate_limit_per_day'] ?? '' ); ?>" class="small-text" /></label>
                        </div>
                    </div>
                    <?php endforeach; ?>
                </div>

                <!-- Emit Targets -->
                <div class="ctxt-card">
                    <h2>Compiler Targets</h2>
                    <p class="description">Which protocol surfaces should the plugin emit?</p>
                    <div class="ctxt-emit-grid">
                        <?php
                        $emit_opts = array(
                            'robots-txt'      => 'robots.txt user-agent groups',
                            'aipref-header'   => 'AIPREF Content-Usage HTTP header',
                            'aipref-robots'   => 'AIPREF rules in robots.txt',
                            'x-robots-tag'    => 'X-Robots-Tag HTTP header',
                            'google-extended' => 'Google-Extended robots.txt block',
                            'tdmrep'          => 'TDMRep Link header (EU)',
                        );
                        foreach ( $emit_opts as $ek => $el ) : ?>
                        <label><input type="checkbox" name="emit[]" value="<?php echo esc_attr($ek); ?>" <?php checked( in_array($ek, $s['emit'] ?? array(), true) ); ?> /> <?php echo esc_html($el); ?></label>
                        <?php endforeach; ?>
                    </div>
                </div>

                <!-- Endpoints -->
                <div class="ctxt-card">
                    <h2>Endpoints <span class="ctxt-badge">Optional</span></h2>
                    <table class="form-table">
                        <tr><th>Payment</th><td><input type="url" name="endpoint_payment" value="<?php echo esc_attr($s['endpoint_payment']); ?>" class="regular-text" /></td></tr>
                        <tr><th>Receipts</th><td><input type="url" name="endpoint_receipts" value="<?php echo esc_attr($s['endpoint_receipts']); ?>" class="regular-text" /></td></tr>
                        <tr><th>Verification</th><td><input type="url" name="endpoint_verification" value="<?php echo esc_attr($s['endpoint_verification']); ?>" class="regular-text" /></td></tr>
                        <tr><th>TDM Policy</th><td><input type="url" name="endpoint_tdm_policy" value="<?php echo esc_attr($s['endpoint_tdm_policy']); ?>" class="regular-text" /></td></tr>
                    </table>
                </div>

                <!-- Custom JSON -->
                <div class="ctxt-card">
                    <h2>Custom JSON Override <span class="ctxt-badge">Advanced</span></h2>
                    <label class="ctxt-toggle" style="margin-bottom:10px;">
                        <input type="checkbox" name="use_custom_json" value="1" <?php checked($s['use_custom_json']); ?> />
                        <span class="ctxt-toggle-track"></span>
                        Serve raw JSON instead of generated manifest
                    </label>
                    <textarea name="custom_json" rows="12" class="large-text code"><?php echo esc_textarea($s['custom_json']); ?></textarea>
                </div>

                <?php submit_button( 'Save & Publish', 'primary large', 'consent_txt_save' ); ?>
            </div>

            <!-- Preview -->
            <div class="ctxt-sidebar">
                <div class="ctxt-card ctxt-card--sticky">
                    <h2>Live Manifest</h2>
                    <pre id="ctxt-preview" class="ctxt-code"><?php echo esc_html( $preview ); ?></pre>
                    <div style="margin-top:10px;display:flex;gap:8px;">
                        <button type="button" class="button" id="ctxt-copy">Copy</button>
                        <a href="<?php echo esc_url($live_url); ?>" target="_blank" class="button">View Live</a>
                    </div>
                </div>
            </div>
        </div>
    </form>
</div>

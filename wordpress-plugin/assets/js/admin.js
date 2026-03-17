(function($) {
    'use strict';

    function applyPreset(key) {
        var preset = consentTxt.presets[key];
        if (!preset || !preset.settings) return;
        var s = preset.settings;

        // Standard categories.
        $.each(s.standard || {}, function(cat, val) {
            $('select[name="standard[' + cat + '][state]"]').val(val.state).trigger('change');
            var panel = $('#std-cond-' + cat);
            if (val.conditions) {
                $.each(val.conditions, function(k, v) {
                    var input = panel.find('[name*="[conditions][' + k + ']"]');
                    if (input.is(':checkbox')) input.prop('checked', !!v);
                    else if (input.is('select')) input.val(v);
                    else input.val(v);
                });
            }
        });

        // Experimental — reset all to unknown first.
        $('select[name^="experimental["]').val('unknown').trigger('change');
        $.each(s.experimental || {}, function(cat, val) {
            $('select[name="experimental[' + cat + '][state]"]').val(val.state).trigger('change');
        });

        // Emit targets.
        $('input[name="emit[]"]').prop('checked', false);
        $.each(s.emit || [], function(_, target) {
            $('input[name="emit[]"][value="' + target + '"]').prop('checked', true);
        });

        $('.ctxt-preset').removeClass('active');
        $('.ctxt-preset[data-preset="' + key + '"]').addClass('active');
        updatePreview();
    }

    function updatePreview() {
        var m = {version: '0.1'};
        m.publisher = {
            name: $('#publisher_name').val() || consentTxt.siteName,
            url: $('#publisher_url').val() || consentTxt.siteUrl,
            contact: $('#publisher_contact').val() || 'mailto:' + consentTxt.email
        };
        var j = $('#jurisdictions').val();
        if (j) m.publisher.jurisdictions = j.split(',').map(function(s){return s.trim();});
        var tu = $('#terms_url').val();
        if (tu) m.publisher.terms_url = tu;

        m.defaults = {};
        m.defaults.fallbacks = {
            unexpressible_state: $('select[name="fallback_unexpressible"]').val(),
            unknown_identity: $('select[name="fallback_unknown_id"]').val()
        };

        var std = {};
        $('select[name^="standard["]').filter('[name$="[state]"]').each(function() {
            var name = $(this).attr('name');
            var cat = name.match(/standard\[([^\]]+)\]/)[1];
            var state = $(this).val();
            if (state === 'unknown') return;
            var entry = {state: state};
            if (state === 'conditional' || state === 'charge') {
                var conds = collectConditions('standard', cat);
                if (Object.keys(conds).length) entry.conditions = conds;
            }
            std[cat] = entry;
        });
        if (Object.keys(std).length) m.defaults.standard = std;

        var exp = {};
        $('select[name^="experimental["]').filter('[name$="[state]"]').each(function() {
            var name = $(this).attr('name');
            var cat = name.match(/experimental\[([^\]]+)\]/)[1];
            var state = $(this).val();
            if (state === 'unknown') return;
            exp[cat] = {state: state};
        });
        if (Object.keys(exp).length) m.defaults.experimental = exp;

        var emit = [];
        $('input[name="emit[]"]:checked').each(function() { emit.push($(this).val()); });
        if (emit.length) m.interop = {emit: emit};

        var endpoints = {};
        ['payment','receipts','verification','tdm_policy'].forEach(function(k) {
            var v = $('input[name="endpoint_' + k + '"]').val();
            if (v) endpoints[k] = v;
        });
        if (Object.keys(endpoints).length) m.endpoints = endpoints;

        $('#ctxt-preview').text(JSON.stringify(m, null, 2));
    }

    function collectConditions(tier, cat) {
        var panel = $('#' + (tier === 'standard' ? 'std' : 'exp') + '-cond-' + cat);
        var conds = {};
        panel.find('input, select').each(function() {
            var name = $(this).attr('name') || '';
            var match = name.match(/\[conditions\]\[([^\]]+)\]/);
            if (!match) return;
            var key = match[1];
            if ($(this).is(':checkbox')) {
                if ($(this).is(':checked')) conds[key] = true;
            } else {
                var val = $(this).val();
                if (val === '' || val === null) return;
                if (/^\d+$/.test(val)) conds[key] = parseInt(val, 10);
                else conds[key] = val;
            }
        });
        return conds;
    }

    $(document).ready(function() {
        // Presets.
        $(document).on('click', '.ctxt-preset', function() {
            applyPreset($(this).data('preset'));
        });

        // Show/hide condition panels.
        $(document).on('change', '.ctxt-state-select', function() {
            var target = $(this).data('target');
            var state = $(this).val();
            if (state === 'conditional' || state === 'charge') {
                $('#' + target).slideDown(150);
            } else {
                $('#' + target).slideUp(150);
            }
            updatePreview();
        });

        // Any change updates preview.
        $(document).on('change input', '#ctxt-form input, #ctxt-form select, #ctxt-form textarea', updatePreview);

        // Copy.
        $('#ctxt-copy').on('click', function() {
            navigator.clipboard.writeText($('#ctxt-preview').text()).then(function() {
                $('#ctxt-copy').text('Copied!');
                setTimeout(function() { $('#ctxt-copy').text('Copy'); }, 1200);
            });
        });

        updatePreview();
    });
})(jQuery);

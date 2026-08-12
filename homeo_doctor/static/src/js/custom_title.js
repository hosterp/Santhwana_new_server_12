odoo.define('homeo_doctor.title', function (require) {
    "use strict";

    var WebClient = require('web.WebClient');
    var FormController = require('web.FormController');
    var session = require('web.session');
    const FormRenderer = require('web.FormRenderer');

    FormRenderer.include({

        _renderView: function () {
            const res = this._super.apply(this, arguments);

            // Check admin access first
            session.user_has_group('base.group_system').then(isAdmin => {
                if (!isAdmin) {
                    setTimeout(() => {
                        this._restrictBillDate();
                    }, 200);
                }
            });

            return res;
        },

        _restrictBillDate: function () {
            const today = moment().startOf('day');

            this.$el
                .find('input.o_datepicker_input[name="bill_date"], input.o_datepicker_input[name="date"],input.o_datepicker_input[name="appointment_date"],input.o_datepicker_input[name="time"]')
                .each(function () {
                    const $input = $(this);
                    const $picker = $input.closest('.o_datepicker');

                    if ($picker.length && $picker.data('datetimepicker')) {
                        // ⛔ Disable past dates (only today allowed)
                        $picker.datetimepicker('minDate', today);
                        // $picker.datetimepicker('maxDate', today);
                    } else {
                        const todayStr = today.format('YYYY-MM-DD');
                        $input.attr('min', todayStr);
                        $input.attr('max', todayStr);
                    }
                });
        },
    });
    WebClient.include({
        set_title_part: function (part, title) {
            var parts = this.get('title_part');
            parts = _.extend({}, parts);
            if (title === undefined) {
                delete parts[part];
            } else {
                parts[part] = title;
            }
            parts['zopenerp'] = false;  // This removes "Odoo" from the title
            this.set('title_part', parts);
            return this._super.apply(this, arguments);
        },

        _title_changed: function () {
            var parts = _.sortBy(_.keys(this.get('title_part')));
            var title = '';
            _.each(parts, function(part) {
                var str = this.get('title_part')[part];
                if (str && part !== 'zopenerp') {  // Skip the Odoo part
                    title = str;
                }
            }.bind(this));
            document.title = title || '';  // Set title to form/menu name only
        }
    });
      const RESTRICTED_MODELS = [
        'patient.appointment',
        'patient.wallet',
        'casuality.billing',
        'pharmacy.description',
        'stock.entry',
        'account.move',
        'ot.billing',
        'pharmacy.return',
        'stock.transfer',
        'audiology.billing',
        'xray.billing',
        'doctor.lab.report',
    ];

    FormController.include({
        renderButtons: function () {
            this._super.apply(this, arguments);

            if (!this.$buttons || !this.modelName) {
                return;
            }

            // Apply only to selected models
            if (!RESTRICTED_MODELS.includes(this.modelName)) {
                return;
            }

            Promise.all([
                session.user_has_group('base.group_system'), // Admin
                session.user_has_group('homeo_doctor.group_allowed_edit'), // Allowed users
            ]).then((results) => {
                const isAdmin = results[0];
                const hasAllowedGroup = results[1];

                // Hide Edit button if NOT admin and NOT allowed group
                if (!isAdmin && !hasAllowedGroup) {
                    this.$buttons.find('.o_form_button_edit').hide();
                }

                // Hide Save and Discard buttons for patient.appointment only for non-editors
                if (this.modelName === 'patient.appointment') {
                    if (!isAdmin && !hasAllowedGroup) {
                        this.$buttons.find('.o_form_button_save').hide();
                        this.$buttons.find('.o_form_button_cancel').hide();
                    }
                }
            });
        },
    });
});
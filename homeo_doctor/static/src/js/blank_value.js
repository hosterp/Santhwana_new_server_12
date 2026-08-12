odoo.define('homeo_doctor.float_no_default', function (require) {
    "use strict";

    var FieldInteger = require('web.basic_fields').FieldInteger;
    var fieldRegistry = require('web.field_registry');

    var FloatNoDefaultWidget = FieldInteger.extend({
        /**
         * @override
         */
        _renderReadonly: function () {
            // Don't display anything if the value is 0 or false
            if (this.value === 0 || this.value === false) {
                this.$el.text('');
            } else {
                this._super.apply(this, arguments);
            }
        },

        /**
         * @override
         */
        _renderEdit: function () {
            this._super.apply(this, arguments);
            // Clear the input if the value is 0 or false
            if (this.value === 0 || this.value === false) {
                this.$input.val('');
            }
        },

        /**
         * @override
         */
        _parseValue: function (value) {
            if (value === '') {
                return false;
            }
            return this._super.apply(this, arguments);
        }
    });

    fieldRegistry.add('float_no_default', FloatNoDefaultWidget);

    return FloatNoDefaultWidget;
});
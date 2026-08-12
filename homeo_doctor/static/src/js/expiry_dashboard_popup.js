odoo.define('homeo_doctor.expiry_dashboard_popup', function (require) {
    "use strict";

    var WebClient = require('web.WebClient');
    var rpc = require('web.rpc');

    WebClient.include({
        start: function () {
            var self = this;
            var res = this._super.apply(this, arguments);

            // Call backend to get expiry message
            rpc.query({
                model: 'dashboard.model',
                method: 'get_expiry_notifications',
            }).then(function(message) {
                if (message) {
                    self.do_notify(
                        'Expiry Warning', // Title
                        message,          // Message
                        true              // sticky: stays until closed
                    );
                }
            });

            return res;
        },
    });
});

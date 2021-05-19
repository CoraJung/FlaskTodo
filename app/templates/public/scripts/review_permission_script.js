
// hide user email when ReviewPermission is not checked
$('#reviewPermissionCheck').change(function() {
    if (this.checked) {
        $("#user_email_div").show();
    } else {
        $("#user_email_div").hide();
    }
});


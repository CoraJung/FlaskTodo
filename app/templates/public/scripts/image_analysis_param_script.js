
// hide max proportion exposed edge when cleanup is not checked
$('#customCheck1').change(function() {
    if (this.checked) {
        $("#conditional_part").show();
    } else {
        $("#conditional_part").hide();
    }
});

// change class name as image type buttons selected

var btn_list = Array.from($('.img-type-btn'));

var setButtons = event => {
    // reset button styles
    btn_list.forEach(_ => _.className = 'img-type-btn btn btn-outline-primary');

    var target = event.target;
    if (!target) return;

    // set target button style
    target.className = 'img-type-btn btn btn-primary';
    
    // set image type formData
    var inputField = $('#imageTypeInput')[0];
    inputField.value = target.id;
}

btn_list.forEach(element => {
    if (!element.addEventListener) return;
    if (typeof element.addEventListener !== 'function') return;
    
    element.addEventListener('click', setButtons);
})

// limit input value type on hole fill area to positive numbers and inf only
var limitOnlyNum = event => {
    var target = event.target;
    var value = target.value;

    if (value === "inf"){return};
    if (value == +value){return};
    
    target.value = "inf";
}

$("#holefillarea")[0].addEventListener('change', limitOnlyNum);

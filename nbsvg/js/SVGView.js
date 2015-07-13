define(["jquery", "widgets/js/widget"], function($, widget) {

    var SVGView = widget.DOMWidgetView.extend({

        render: function(){
            this.$svg = $('<svg>');
            this.$el.append(this.$svg);
            this.svg_changed();
            this.$el.attr({overflow: 'hidden'});
            this.model.on('change:svg', this.svg_changed, this);
        },

        svg_changed: function() {
            this.$svg.html(this.model.get('svg'))
        },
    });

    return {SVGView: SVGView};
});
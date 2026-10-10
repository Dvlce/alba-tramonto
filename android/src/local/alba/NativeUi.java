package local.alba;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.Drawable;
import android.widget.Button;
import android.widget.TextView;

/** Shared native tokens for the approved dark and light interfaces. */
final class NativeUi {
    final boolean light;
    final int bg,surface,soft,line,ink,muted,primary,onPrimary;
    static final int PAPER=0xfffcfaf2,PAPER_INK=0xff2a432f;
    NativeUi(Context context){
        light=context.getSharedPreferences("alba",0).getBoolean("light_theme",false);
        bg=light?0xfff4f5ee:0xff101b16;surface=light?0xfffffef9:0xff1b2a21;
        soft=light?0xffe7edde:0xff25372c;line=light?0xffdfe5d9:0xff2c3c31;
        ink=light?0xff243b2c:0xffecf0e7;muted=light?0xff74816f:0xff9aa99b;
        primary=light?0xff476844:0xffb2ce9a;onPrimary=light?0xfffffef9:0xff233421;
    }
    static int dp(Context context,int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context context,int color,int radius,int border){
        GradientDrawable value=new GradientDrawable();value.setColor(color);value.setCornerRadius(dp(context,radius));
        if(border!=0)value.setStroke(dp(context,1),border);return value;
    }
    static Drawable touch(Context context,int color,int radius,int border){
        NativeUi ui=new NativeUi(context);
        return new RippleDrawable(ColorStateList.valueOf((ui.primary&0xffffff)|0x22000000),shape(context,color,radius,border),shape(context,0xffffffff,radius,0));
    }
    static void button(Button view,boolean primary){
        Context context=view.getContext();NativeUi ui=new NativeUi(context);
        view.setAllCaps(false);view.setTextSize(13);view.setTypeface(android.graphics.Typeface.create("sans-serif-medium",0));
        view.setTextColor(primary?ui.onPrimary:ui.ink);view.setMinHeight(dp(context,44));view.setMinimumHeight(dp(context,44));
        view.setMinWidth(0);view.setMinimumWidth(0);view.setPadding(dp(context,16),0,dp(context,16),0);
        view.setBackground(touch(context,primary?ui.primary:ui.surface,22,primary?0:ui.line));
        view.setStateListAnimator(null);
    }
    static void text(TextView view,int size,boolean muted){NativeUi ui=new NativeUi(view.getContext());view.setTextSize(size);view.setTextColor(muted?ui.muted:ui.ink);view.setIncludeFontPadding(false);}
}

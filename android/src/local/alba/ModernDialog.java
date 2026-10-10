package local.alba;

import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.TextView;

/** Rounded, themed sheets for both existing tools and the new primary flows. */
final class ModernDialog {
    static class Builder extends AlertDialog.Builder {
        private final Context owner;
        Builder(Context context){super(context,new NativeUi(context).light?R.style.AlbaDialogLight:R.style.AlbaDialogDark);owner=context;}
        @Override public AlertDialog create(){
            AlertDialog dialog=super.create();
            dialog.setOnShowListener(ignored->{
                NativeUi ui=new NativeUi(owner);Window window=dialog.getWindow();if(window==null)return;
                window.setBackgroundDrawable(NativeUi.shape(owner,ui.surface,28,ui.line));window.setGravity(Gravity.BOTTOM);
                window.setLayout(owner.getResources().getDisplayMetrics().widthPixels-NativeUi.dp(owner,16),WindowManager.LayoutParams.WRAP_CONTENT);
                WindowManager.LayoutParams p=window.getAttributes();p.y=NativeUi.dp(owner,8);p.dimAmount=.45f;window.setAttributes(p);
                window.getDecorView().setElevation(NativeUi.dp(owner,12));
                int titleId=owner.getResources().getIdentifier("alertTitle","id","android");TextView title=dialog.findViewById(titleId);
                if(title!=null){title.setTextSize(20);title.setTextColor(ui.ink);title.setTypeface(android.graphics.Typeface.create("sans-serif-medium",0));}
                TextView message=dialog.findViewById(android.R.id.message);if(message!=null){message.setTextColor(ui.ink);message.setTextSize(15);message.setLineSpacing(NativeUi.dp(owner,3),1.1f);}
                for(int which:new int[]{AlertDialog.BUTTON_POSITIVE,AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL}){
                    Button button=dialog.getButton(which);if(button!=null){NativeUi.button(button,which==AlertDialog.BUTTON_POSITIVE);button.setTextSize(12);}
                }
                if(dialog.getListView()!=null){dialog.getListView().setDivider(null);dialog.getListView().setPadding(NativeUi.dp(owner,8),0,NativeUi.dp(owner,8),0);}
            });return dialog;
        }
    }
}
